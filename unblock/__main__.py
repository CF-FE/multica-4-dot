"""Run one bounded reconciliation pass over explicitly registered cases."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


SCOPE = ("instance_id", "workspace_id", "project_id", "issue_id", "thread_id")


def scope_key(registration):
    parts = [registration.get(key) for key in SCOPE]
    if not all(isinstance(part, str) and part.strip() == part and part for part in parts):
        raise ValueError("incomplete case scope")
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def _catalog_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate catalog field")
    return result


def _canonical_uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def registrations(path, *, require_workspace_coordinators=False, require_live_appointments=False):
    """Resolve the workspace's coordinator before selecting individual cases."""
    catalog = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_catalog_object)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("projects"), list):
        raise ValueError("expected a projects array")
    has_registry = "workspace_coordinators" in catalog
    live = catalog.get("appointment_ssh_config")
    if "appointment_ssh_config" in catalog and (not isinstance(live, str) or not Path(live).is_absolute()):
        raise ValueError("invalid appointment SSH configuration")
    if live and has_registry:
        raise ValueError("ambiguous coordinator authority")
    if require_live_appointments and not live:
        raise ValueError("live workspace appointment source required")
    if require_workspace_coordinators and not (has_registry or live):
        raise ValueError("missing workspace coordinator registry")
    workspace_coordinators = catalog.get("workspace_coordinators", {})
    if not isinstance(workspace_coordinators, dict) or any(
        not instance or instance.strip() != instance or not isinstance(workspaces, dict)
        or any(not _canonical_uuid(workspace) or not _canonical_uuid(coordinator)
               for workspace, coordinator in workspaces.items())
        for instance, workspaces in workspace_coordinators.items()
    ):
        raise ValueError("invalid workspace coordinator registry")
    result = []
    seen = set()
    current_coordinators = {}
    for project in catalog["projects"]:
        if not isinstance(project, dict):
            raise ValueError("invalid project registration")
        defaults = project.get("defaults")
        cases = project.get("cases")
        if not isinstance(defaults, dict) or not isinstance(cases, list):
            raise ValueError("expected project defaults and cases")
        instance, workspace, project_id = (defaults.get(key) for key in SCOPE[:3])
        if not all(isinstance(value, str) and value and value.strip() == value
                   for value in (instance, workspace, project_id)):
            raise ValueError("missing project binding")
        workspace_key = (instance, workspace.lower())
        appointed = workspace_coordinators.get(instance, {}).get(workspace_key[1])
        coordinator = defaults.get("coordinator_id", appointed)
        if not live and not _canonical_uuid(coordinator):
            raise ValueError("missing or invalid project coordinator binding")
        for case in cases:
            if (not isinstance(case, dict) or "coordinator_id" in case or defaults.keys() & case.keys()
                    or {"appointment_ssh_config", "_live_appointment", "_appointment_cached",
                        "_appointment_checked_at"} & (case.keys() | defaults.keys())):
                raise ValueError("case overlaps project-owned fields")
            reg = {**defaults, **case}
            if live:
                reg["appointment_ssh_config"] = live
                reg.pop("coordinator_id", None)
            else:
                reg["coordinator_id"] = coordinator
            if not live and reg.get("notifications_enabled") is True:
                if has_registry and appointed != coordinator:
                    raise ValueError("current case must use the appointed workspace coordinator")
                if current_coordinators.setdefault(workspace_key, coordinator) != coordinator:
                    raise ValueError("conflicting current coordinator bindings in one workspace")
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
    issue_closed = observation.get("issue_closed")
    if issue_closed is not None and type(issue_closed) is not bool:
        raise ValueError("invalid Issue status coverage")
    if issue_closed is None and "issue_status_unconfirmed" not in pending:
        pending = [*pending, "issue_status_unconfirmed"]
    assessment = assess(reg, observation["snapshot"], now,
                        pickup_source_verified=observation.get("pickup_source_verified", False))
    return assessment, hints, pending, observation["snapshot"], observation.get("summary_source"), issue_closed


def should_notify(assessment, hints):
    return assessment["notification_open"] is True and (bool(hints) or assessment["checkpoint_due"] is True)


def run_case(reg, source, *, apply, db_path=None, clock=None):
    from .ledger import reconcile, reconcile_existing

    clock = clock or (lambda: datetime.now(timezone.utc))
    key = scope_key(reg)
    result, hints, pending, signed, origin, issue_closed = inspect_case(reg, source, clock())
    output = {"scope": json.loads(key), "assessment": result, "hints": hints, "pending": pending,
              "basis": "coordinator_reviewed_summary", "summary_source": origin, "issue_closed": issue_closed}
    if pending:
        output["notification"] = "source_unconfirmed"
        return output
    if issue_closed is True or not should_notify(result, hints):
        output["notification"] = "quiet"
        return output
    output["notification"] = "preview"
    if apply:
        if reg.get("notifications_enabled") is not True:
            output["notification"] = "disabled"
            return output
        if db_path is None:
            raise ValueError("a persistent ledger is required to notify")
        existing = reconcile_existing(db_path, key, result["checkpoint_id"], source.lookup)
        if existing["status"] != "not_found":
            output["notification"] = existing
            return output
    if result["activity"] != "clear":
        output.update(notification="deferred", hold_reason="issue_activity_unconfirmed")
        return output
    if not apply:
        return output

    # Re-read before claiming. A new signed revision can withdraw the action.
    current, current_hints, current_pending, latest, current_origin, current_closed = inspect_case(reg, source, clock())
    if (signed != latest or origin != current_origin or current["next_action"] != result["next_action"]
            or current_pending or current_closed is True or current["activity"] != "clear"
            or not should_notify(current, current_hints)):
        output.update(assessment=current, hints=current_hints, pending=current_pending, summary_source=current_origin,
                      issue_closed=current_closed, notification="source_unconfirmed" if current_pending else "changed")
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
        sub.add_argument("--thread", help="Restrict an Issue to one registered root comment")
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


def main(argv=None, *, registered=None):
    args = parser().parse_args(argv)
    if args.command == "verify-copy":
        from .artifact import verify_copy

        proof = verify_copy(args.source_root, args.source_relative, args.target_root, args.target_relative,
                            args.expected_bytes, args.expected_sha256)
        print(json.dumps(proof, ensure_ascii=False))
        return 0 if proof["status"] == "match_existing" else 1

    catalog = registrations(args.config) if registered is None else registered
    has_issue = args.issue is not None
    has_thread = args.thread is not None
    if has_thread and not has_issue:
        raise ValueError("--thread requires --issue")
    selected = [
        reg for reg in catalog
        if (not has_issue or reg["issue_id"] == args.issue)
        and (not has_thread or reg["thread_id"] == args.thread)
    ]
    exact_case = has_thread or args.command in ("recover", "prepare-note") or (
        has_issue and args.command == "tick" and args.apply
    )
    if exact_case and len(selected) != 1:
        raise ValueError("expected exactly one registered case; use --issue and --thread to select it")
    if has_issue and not selected:
        raise ValueError("no registered case for that Issue")
    if args.command == "tick" and args.apply and not args.db:
        raise ValueError("--apply requires a persistent --db")
    from .appointment import AppointmentScan, AppointmentUnavailable
    from .native import NativeSource, NativeSourceError
    results, incomplete = [], False
    appointments = AppointmentScan(args.db if args.command == "tick" and args.apply else None)
    for reg in selected:
        try:
            if "appointment_ssh_config" in reg and args.command != "recover":
                reg = appointments.bind(reg)
            if args.command == "prepare-note":
                from .model import assess

                snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
                assess(reg, snapshot, datetime.now(timezone.utc))
                print("/note unblock.v1 " + json.dumps(snapshot, ensure_ascii=False, allow_nan=False,
                                                        separators=(",", ":")))
                return 0
            if args.command == "recover":
                from .ledger import reconcile_existing

                source = NativeSource(reg, recovery_only=True)
                receipt = reconcile_existing(args.db, scope_key(reg), args.checkpoint, source.lookup)
                results.append({"scope": json.loads(scope_key(reg)), "notification": receipt})
            else:
                apply = args.command == "tick" and args.apply
                source = NativeSource(reg, appointment_reader=appointments.refresh)
                try:
                    row = run_case(reg, source, apply=apply, db_path=getattr(args, "db", None))
                except NativeSourceError as exc:
                    if exc.code != "coordinator_refresh_required" or not reg.get("_appointment_cached"):
                        raise
                    appointments.refresh(reg["appointment_ssh_config"], reg["instance_id"], reg["workspace_id"])
                    reg = appointments.bind(reg)
                    source = NativeSource(reg, appointment_reader=appointments.refresh)
                    row = run_case(reg, source, apply=apply, db_path=getattr(args, "db", None))
                if row["pending"]:
                    incomplete = True
                assessment = row["assessment"]
                owned_by_g8 = (assessment["g8_status"] == "accepted"
                               and assessment["next_action"] in ("follow_g8_plan", "recheck_g8_plan")
                               and assessment["owner_id"] == reg["roles"].get("g8", {}).get("id"))
                if args.command == "g8":
                    pickup_pending = assessment["state"] == "awaiting_pickup" and assessment["notification_open"]
                    if row.get("issue_closed") is True or not (
                        assessment["g8_pending"] or owned_by_g8 or row["pending"] or pickup_pending
                    ):
                        continue
                results.append(row)
        except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
            if args.command == "prepare-note":
                raise
            # Individual cases can have different grants. Preserve the incomplete scope and
            # a diagnostic without passing through subprocess output or private source text.
            incomplete = True
            row = {"scope": json.loads(scope_key(reg)), "state": "unconfirmed",
                   "error_type": type(exc).__name__}
            if isinstance(exc, NativeSourceError):
                row["reason"] = exc.code
            if isinstance(exc, AppointmentUnavailable):
                row["reason"] = "coordinator_appointment_unconfirmed"
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
