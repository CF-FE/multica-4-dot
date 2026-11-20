"""Read the receiver's native note and independently establish Run startup."""

from datetime import datetime
import json

from .delivery import IssueReference
from .multica_api import _match_id, _status, _uuid, _verify_run_scope
from .native_http import NativeHTTP, NativeHTTPError


def _timestamp(value: object) -> datetime:
    if isinstance(value, str) and "T" in value:
        try:
            timestamp = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if timestamp.tzinfo is not None:
                return timestamp
    raise NativeHTTPError("intake_evidence", "schema_drift")


def _read_rows(http: NativeHTTP, issue: IssueReference, resource: str, *, incomplete_headers=()) -> list[dict]:
    rows = http.request("GET", f"/api/issues/{issue.issue_id}/{resource}", workspace_id=issue.workspace_id,
                        incomplete_headers=incomplete_headers)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise NativeHTTPError("intake_evidence", "schema_drift")
    return rows


def read_receipt(http: NativeHTTP, issue: IssueReference, *, job_id: str, payload_hash: str,
                 coordinator_id: str) -> dict:
    """Accept one live top-level /note, authored by the frozen coordinator in Multica."""
    expected = {"event": "mailbox-intake-v1", "job_id": job_id, "payload_hash": payload_hash,
                "issue_id": issue.issue_id, "coordinator_id": coordinator_id}
    try:
        rows = _read_rows(http, issue, "comments?roots_only=true",
                          incomplete_headers=("X-Comments-Truncated", "X-Multica-Next-Before"))
        receipts = []
        for row in rows:
            _match_id(row, "issue_id", issue.issue_id, "intake_comment")
            if (row.get("author_type") != "agent" or row.get("author_id") != coordinator_id
                    or row.get("type") != "comment" or "parent_id" not in row or row["parent_id"] is not None
                    or row.get("deleted_at") is not None):
                continue
            content = row.get("content")
            if not isinstance(content, str) or not content.startswith("/note "):
                continue
            try:
                # Retain the top-level pairs so duplicate keys cannot attest to a job.
                fields = json.loads(content[6:], object_pairs_hook=tuple)
            except (ValueError, RecursionError):
                continue
            if not isinstance(fields, tuple) or len(fields) != len(expected) or dict(fields) != expected:
                continue
            _timestamp(row.get("created_at"))
            receipt = {"id": _uuid(row.get("id"), "intake_comment", "id"), "author_type": "agent",
                       "author_id": coordinator_id, "created_at": row["created_at"]}
            if row.get("source_task_id") is not None:
                try:
                    receipt["source_task_id"] = _uuid(row["source_task_id"], "intake_comment", "source_task_id")
                except NativeHTTPError:
                    # The source Run can be unavailable without invalidating the agent's note.
                    pass
            receipts.append(receipt)
    except NativeHTTPError as exc:
        return {"state": "unconfirmed", "reason": exc.code}
    if len(receipts) == 1:
        return {"state": "accepted", "receipt": receipts[0]}
    return {"state": "unconfirmed", "reason": "receipt_ambiguous" if receipts else "receipt_not_observed"}


def read_intake_run(http: NativeHTTP, issue: IssueReference, *, coordinator_id: str, receipt: dict) -> dict:
    """Read the exact Run that authored the scoped job receipt via its native task token."""
    try:
        rows = _read_rows(http, issue, "task-runs?scope=issue&view=timeline",
                          incomplete_headers=("X-Active-Runs-Truncated",))
        candidates, bound = [], None
        source_task_id = receipt.get("source_task_id")
        seen = set()
        for row in rows:
            run_id = _verify_run_scope(row, issue_id=issue.issue_id, workspace_id=issue.workspace_id,
                                       project_id=issue.project_id, seen=seen)
            if _uuid(row.get("agent_id"), "intake_run", "agent_id") != coordinator_id:
                continue
            candidates.append({"id": run_id, "status": _status(row, "intake_run")})
            if run_id == source_task_id:
                bound = row
        if bound is None:
            if len(candidates) == 1:
                return {"state": "unconfirmed", "reason": "run_source_unverified", "candidate": candidates[0]}
            return {"state": "unconfirmed", "reason": "run_ambiguous" if candidates else "run_not_observed"}
        if bound["status"] == "queued":
            return {"state": "queued", "id": source_task_id}
        if bound.get("started_at") is None:
            return {"state": "unconfirmed", "reason": "run_start_not_observed", "id": source_task_id}
        started = _timestamp(bound["started_at"])
        accepted = _timestamp(receipt["created_at"])
        if not _timestamp(bound.get("created_at")) <= started <= accepted:
            raise NativeHTTPError("intake_run", "invalid_start_time")
        if bound.get("completed_at") is not None and _timestamp(bound["completed_at"]) < accepted:
            raise NativeHTTPError("intake_run", "receipt_after_run_completion")
        return {"state": "started", "id": source_task_id, "started_at": bound["started_at"],
                "basis": "receipt_source_task"}
    except NativeHTTPError as exc:
        return {"state": "unconfirmed", "reason": exc.code}
