"""Run the VPS deployment with its private registration and persisted ledger."""

import argparse
from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import re
import sqlite3
import sys


CONFIG = Path("/etc/multica-unblock/cases.json")
DATABASE = Path("/var/lib/multica-unblock/checkpoints.sqlite3")
APP = Path(__file__).resolve().with_name("app")

UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
CHECKPOINT = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
MARKER = r"unblock\.v1:[0-9a-f]{64}"
STARTED_AT = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})"
NOTIFICATION_STATES = {
    "source_unconfirmed", "quiet", "preview", "disabled", "changed", "deferred",
    "confirmed", "unknown", "not_found",
}
ERROR_TYPES = {"NativeSourceError", "ValueError", "OSError", "RuntimeError", "Error", "OperationalError", "DatabaseError"}
DIAGNOSTICS = set("""
    ambiguous_current_summary ambiguous_handoff_comments ambiguous_summary_revision ambiguous_thread
    ambiguous_wakeup ambiguous_wakeup_run bad_request cli_read_failed comment_scope_mismatch
    comment_thread_mismatch conflict coordinator_changed coordinator_appointment_unconfirmed
    coordinator_request_conflict pickup_source_unconfirmed issue_activity_unconfirmed
    coordinator_appointment_changed previous_coordinator_wakeup_active recovery_only_source
    coordinator_appointment_inactive coordinator_summary_unconfirmed
    coordinator_wakeup_already_active duplicate_run duplicate_wakeup edited_summary edited_supplement
    evidence_reference_unconfirmed exact_run_unconfirmed forbidden handoff_comment_not_top_level
    handoff_comment_scope_mismatch handoff_comment_truncated http_error identity_mismatch incomplete_response
    incomplete_thread invalid_credential invalid_handoff invalid_handoff_evidence_reference
    invalid_handoff_fields invalid_json invalid_native_response invalid_run_status invalid_source_timestamp
    invalid_summary_revision issue_closed_or_paused issue_run_in_flight issue_scope_mismatch
    issue_status_unconfirmed lookup_failed lookup_receipt_invalid mailbox_version_regressed
    mailbox_watermark_unconfirmed multica_credential_unavailable not_configured not_found
    notifications_disabled payload_hash_mismatch poll_snapshot_changed profile_binding_unknown
    profile_origin_mismatch protocol_error receipt_pending recipient_mismatch redirect_refused
    registered_checkpoint_changed response_too_large route_mismatch run_scope_unconfirmed send_failed
    send_receipt_invalid status_catalog_unconfirmed summary_outside_coordinator_appointment
    summary_recorded_after_publication summary_revision_out_of_order summary_scope_mismatch target_mismatch
    thread_root_unconfirmed timeout transport_error unauthenticated unavailable verified_poll_required
    wakeup_marker_conflict wakeup_run_scope_unconfirmed wakeup_scope_mismatch
""".split())


def matching_fields(fields):
    return {key: value for key, (value, pattern) in fields.items()
            if isinstance(value, str) and re.fullmatch(pattern, value)}


def diagnostic(value):
    if not isinstance(value, str):
        return "unrecognized_diagnostic"
    code = re.sub(r"^(?:comment:|mailbox:|run:)?(?:multica:)?", "", value)
    return value if code in DIAGNOSTICS else "unrecognized_diagnostic"


def journal_result(result):
    """Keep only the identifiers and fixed states needed for reminder reconciliation."""
    if not isinstance(result, dict) or not isinstance(result.get("cases"), list):
        raise ValueError("missing case report")
    rows = []
    for case in result["cases"]:
        scope = case.get("scope", [])
        assessment = case.get("assessment") or {}
        source = case.get("summary_source") or {}
        row = matching_fields({
            "issue_id": (scope[3] if isinstance(scope, list) and len(scope) > 3 else None, UUID),
            "checkpoint_id": (assessment.get("checkpoint_id"), CHECKPOINT),
            "summary_comment_id": (source.get("comment_id"), UUID),
        })
        hints = [hint for hint in case.get("hints", [])
                 if isinstance(hint, str) and re.fullmatch(rf"(?:patrol_handoff|comment):{UUID}", hint)]
        if hints:
            row["hints"] = hints
        if case.get("state") == "unconfirmed":
            row["state"] = "unconfirmed"
        error_type = case.get("error_type")
        if isinstance(error_type, str) and error_type in ERROR_TYPES:
            row["error_type"] = error_type
        for key in ("reason", "hold_reason"):
            if key in case:
                row[key] = diagnostic(case[key])
        if case.get("pending"):
            row["pending"] = sorted({diagnostic(reason) for reason in case["pending"]})

        notification = case.get("notification")
        if isinstance(notification, str) and notification in NOTIFICATION_STATES:
            row["notification"] = notification
        elif isinstance(notification, dict):
            receipt = notification.get("receipt") or {}
            safe = matching_fields({"marker": (notification.get("marker"), MARKER)})
            status = notification.get("status")
            if isinstance(status, str) and status in NOTIFICATION_STATES:
                safe["status"] = status
            if "reason" in notification:
                safe["reason"] = diagnostic(notification["reason"])
            receipt_fields = matching_fields({
                "wakeup_id": (receipt.get("wakeup_id"), UUID),
                "run_id": (receipt.get("run_id"), UUID),
                "started_at": (receipt.get("started_at"), STARTED_AT),
            })
            if receipt_fields:
                safe["receipt"] = receipt_fields
            row["notification"] = safe
        rows.append(row)
    report = {"cases": rows}
    if type(result.get("source_reads_complete")) is bool:
        report["source_reads_complete"] = result["source_reads_complete"]
    if type(result.get("notifications_unconfirmed")) is int:
        report["notifications_unconfirmed"] = result["notifications_unconfirmed"]
    return report


def apply_and_log(unblock, argv, registered):
    try:
        with redirect_stdout(StringIO()) as raw, redirect_stderr(StringIO()):
            code = unblock(argv, registered=registered)
    except Exception as exc:
        error_type = type(exc).__name__
        safe_type = error_type if error_type in ERROR_TYPES else "Exception"
        print(f"unblock: apply command failed ({safe_type})", file=sys.stderr)
        return 2
    try:
        print(json.dumps(journal_result(json.loads(raw.getvalue())), ensure_ascii=False))
    except (AttributeError, TypeError, ValueError):
        print("unblock: apply report unavailable", file=sys.stderr)
        return code or 2
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("apply", "preview"))
    parser.add_argument("--issue", required=False)
    args = parser.parse_args()
    if args.mode == "apply" and args.issue:
        parser.error("--issue is only available in preview mode")

    sys.path.insert(0, str(APP))
    from unblock.__main__ import main as unblock, registrations

    registered = registrations(CONFIG, require_live_appointments=True)
    if args.mode == "apply":
        enabled = [case for case in registered if case.get("notifications_enabled") is True]
        if not enabled:
            print("unblock: no notification-enabled cases")
            return 0
        # A forgotten database would lose spent claims, so the service must open the migrated ledger.
        with closing(sqlite3.connect(f"{DATABASE.as_uri()}?mode=ro", uri=True)) as db:
            db.execute("SELECT scope_key, checkpoint_id, marker, receipt_json FROM unblock_notifications LIMIT 0")
            if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
                raise ValueError("notification ledger integrity check failed")

    credential_dir = Path(os.environ["CREDENTIALS_DIRECTORY"])
    token = (credential_dir / "operator-pat").read_text(encoding="utf-8").strip()
    if not token.startswith("mul_"):
        raise ValueError("operator credential format invalid")
    os.environ["MULTICA_UNBLOCK_ACCESS_TOKEN"] = token

    if args.mode == "preview":
        return unblock(["tick", "--config", str(CONFIG), *(["--issue", args.issue] if args.issue else [])],
                       registered=registered)

    return apply_and_log(unblock, ["tick", "--config", str(CONFIG), "--apply", "--db", str(DATABASE)], enabled)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"unblock: deployment preflight failed ({type(exc).__name__})", file=sys.stderr)
        sys.exit(2)
