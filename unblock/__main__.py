"""Run one bounded reconciliation pass over explicitly registered cases."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SCOPE = ("instance_id", "workspace_id", "project_id", "issue_id", "thread_id")


def scope_key(registration):
    parts = [registration.get(key) for key in SCOPE]
    if not all(isinstance(part, str) and part.strip() == part and part for part in parts):
        raise ValueError("incomplete case scope")
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def registrations(path):
    """A project shares one authority index; a case cannot override its bindings."""
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("projects"), list):
        raise ValueError("expected a projects array")
    result = []
    seen = set()
    for project in catalog["projects"]:
        if not isinstance(project, dict):
            raise ValueError("invalid project registration")
        defaults = project.get("defaults")
        cases = project.get("cases")
        if not isinstance(defaults, dict) or not isinstance(cases, list):
            raise ValueError("expected project defaults and cases")
        if not all(defaults.get(key) for key in ("instance_id", "workspace_id", "project_id", "coordinator_id")):
            raise ValueError("missing project or coordinator binding")
        for case in cases:
            if not isinstance(case, dict) or defaults.keys() & case.keys():
                raise ValueError("case overlaps project-owned fields")
            reg = {**defaults, **case}
            identity = scope_key(reg)
            if identity in seen:
                raise ValueError("duplicate case registration")
            seen.add(identity)
            result.append(reg)
    return result


def inspect_case(reg, source, now):
    from .model import assess

    observation = source.poll()
    hints = observation["hints"]
    if not isinstance(hints, list) or any(not isinstance(hint, str) or not hint for hint in hints):
        raise ValueError("invalid checkpoint hints")
    pending = observation.get("pending", [])
    if not isinstance(pending, list):
        raise ValueError("invalid source coverage")
    assessment = assess(reg, observation["snapshot"], now)
    return assessment, hints, pending, observation["snapshot"], observation.get("summary_source")


def should_notify(assessment, hints):
    return assessment["notification_open"] is True and (bool(hints) or assessment["checkpoint_due"] is True)


def run_case(reg, source, *, apply, db_path=None, clock=None):
    from .ledger import reconcile, reconcile_existing

    clock = clock or (lambda: datetime.now(timezone.utc))
    key = scope_key(reg)
    result, hints, pending, signed, origin = inspect_case(reg, source, clock())
    output = {"scope": json.loads(key), "assessment": result, "hints": hints, "pending": pending,
              "basis": "coordinator_reviewed_summary", "summary_source": origin}
    if pending:
        output["notification"] = "source_unconfirmed"
        return output
    if not should_notify(result, hints):
        output["notification"] = "quiet"
        return output
    output["notification"] = "preview"
    if not apply:
        return output
    if reg.get("notifications_enabled") is not True:
        output["notification"] = "disabled"
        return output
    if db_path is None:
        raise ValueError("a persistent ledger is required to notify")
    existing = reconcile_existing(db_path, key, result["checkpoint_id"], source.lookup)
    if existing["status"] != "not_found":
        output["notification"] = existing
        return output

    # Re-read before claiming. A new signed revision can withdraw the action.
    current, current_hints, current_pending, latest, current_origin = inspect_case(reg, source, clock())
    if (signed != latest or origin != current_origin or current["next_action"] != result["next_action"]
            or current_pending or not should_notify(current, current_hints)):
        output.update(assessment=current, hints=current_hints, pending=current_pending, summary_source=current_origin,
                      notification="source_unconfirmed" if current_pending else "changed")
        return output
    hold = source.check_ready()
    if hold is not None:
        output.update(notification="deferred", hold_reason=hold)
        return output
    output["notification"] = reconcile(db_path, key, current["checkpoint_id"], source.notify, source.lookup)
    return output


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cmds = cli.add_subparsers(dest="command", required=True)
    for command in ("summary", "g8", "tick", "recover", "prepare-note"):
        sub = cmds.add_parser(command)
        sub.add_argument("--config", required=True, help="Trusted local JSON registration file")
        sub.add_argument("--issue", required=command in ("recover", "prepare-note"),
                         help="Restrict to one registered Issue")
        if command == "prepare-note":
            sub.add_argument("--snapshot", required=True, help="Coordinator-reviewed JSON file to format")
        if command in ("tick", "recover"):
            sub.add_argument("--db", required=command == "recover", help="Private persistent SQLite path")
        if command == "tick":
            sub.add_argument("--apply", action="store_true", help="Allow one registered coordinator notification")
        if command == "recover":
            sub.add_argument("--checkpoint", required=True)
    sub = cmds.add_parser("verify-copy")
    for flag in ("source-root", "source-relative", "target-root", "target-relative", "expected-sha256"):
        sub.add_argument("--" + flag, required=True)
    sub.add_argument("--expected-bytes", type=int, required=True)
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "verify-copy":
        from .artifact import verify_copy

        proof = verify_copy(args.source_root, args.source_relative, args.target_root, args.target_relative,
                            args.expected_bytes, args.expected_sha256)
        print(json.dumps(proof, ensure_ascii=False))
        return 0 if proof["status"] == "match_existing" else 1

    selected = [reg for reg in registrations(args.config) if not args.issue or reg["issue_id"] == args.issue]
    if args.issue and len(selected) != 1:
        raise ValueError("expected exactly one registered case for that Issue")
    if args.command == "tick" and args.apply and not args.db:
        raise ValueError("--apply requires a persistent --db")
    if args.command == "prepare-note":
        from .model import assess

        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        assess(selected[0], snapshot, datetime.now(timezone.utc))
        print("/note unblock.v1 " + json.dumps(snapshot, ensure_ascii=False, allow_nan=False,
                                                separators=(",", ":")))
        return 0

    from .native import NativeSource, NativeSourceError
    results, incomplete = [], False
    for reg in selected:
        try:
            source = NativeSource(reg)
            if args.command == "recover":
                from .ledger import reconcile_existing

                receipt = reconcile_existing(args.db, scope_key(reg), args.checkpoint, source.lookup)
                results.append({"scope": json.loads(scope_key(reg)), "notification": receipt})
            else:
                row = run_case(reg, source, apply=args.command == "tick" and args.apply,
                               db_path=getattr(args, "db", None))
                if row["pending"]:
                    incomplete = True
                assessment = row["assessment"]
                owned_by_g8 = (assessment["g8_status"] == "accepted"
                               and assessment["next_action"] in ("follow_g8_plan", "recheck_g8_plan")
                               and assessment["owner_id"] == reg["roles"].get("g8", {}).get("id"))
                if args.command != "g8" or assessment["g8_pending"] or owned_by_g8 or row["pending"]:
                    results.append(row)
        except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
            # Individual cases can have different grants. Preserve the incomplete scope and
            # a diagnostic without passing through subprocess output or private source text.
            incomplete = True
            row = {"scope": json.loads(scope_key(reg)), "state": "unconfirmed",
                   "error_type": type(exc).__name__}
            if isinstance(exc, NativeSourceError):
                row["reason"] = exc.code
            results.append(row)
    awaiting = sum(isinstance(r.get("notification"), dict) and r["notification"]["status"] == "unknown"
                   for r in results)
    print(json.dumps({"source_reads_complete": not incomplete, "notifications_unconfirmed": awaiting,
                      "cases": results}, ensure_ascii=False))
    return int(incomplete)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"unblock: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
