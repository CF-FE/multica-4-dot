"""Durable claim and reconciliation for a single Multica Issue dispatch."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID


class RequestConflict(ValueError):
    """This authenticated principal already used the request ID for other input."""


class UnverifiedIssue(ValueError):
    """Native evidence does not establish the expected Issue."""


@dataclass(frozen=True)
class NewIssue:
    title: str
    status: str
    description: str = ""

    def __post_init__(self) -> None:
        title, status = self.title.strip(), self.status.strip()
        if not title or not status:
            raise ValueError("title and native status key are required")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "status", status)


@dataclass(frozen=True)
class DispatchCommand:
    """Frozen native route, with exactly one of create or use-original."""

    instance_id: str
    workspace_id: str
    project_id: str
    coordinator_id: str
    new_issue: NewIssue | None = None
    original_issue_id: str | None = None
    mailbox_project_id: str | None = None
    mailbox_job_id: str | None = None
    mailbox_payload_hash: str | None = None
    mailbox_recipient: str | None = None

    def __post_init__(self) -> None:
        if not self.instance_id or self.instance_id != self.instance_id.strip():
            raise ValueError("a canonical configured instance ID is required")
        if (self.new_issue is None) == (self.original_issue_id is None):
            raise ValueError("provide new issue fields or an original issue UUID")
        if bool(self.mailbox_project_id) != bool(self.mailbox_job_id):
            raise ValueError("provide both Mailbox project and job IDs")
        object.__setattr__(self, "mailbox_project_id", self.mailbox_project_id or None)
        object.__setattr__(self, "mailbox_job_id", self.mailbox_job_id or None)
        if (self.mailbox_payload_hash is None) != (self.mailbox_recipient is None):
            raise ValueError("a verified Mailbox reference requires both its hash and recipient")
        if self.mailbox_payload_hash is not None:
            if not self.mailbox_job_id or len(self.mailbox_payload_hash) != 64 or any(
                ch not in "0123456789abcdef" for ch in self.mailbox_payload_hash
            ) or not self.mailbox_recipient.strip():
                raise ValueError("invalid verified Mailbox reference")
        for name in ("workspace_id", "project_id", "coordinator_id", "original_issue_id"):
            value = getattr(self, name)
            if value is not None or name != "original_issue_id":
                object.__setattr__(self, name, str(UUID(value)))


@dataclass(frozen=True)
class IssueReference:
    instance_id: str
    workspace_id: str
    project_id: str
    issue_id: str


@dataclass(frozen=True)
class DeliveryResult:
    """Confirmed means the native Issue was verified. Run evidence is separate."""

    state: Literal["accepted", "unknown", "confirmed"]
    correlation: str
    instance_id: str
    workspace_id: str
    project_id: str
    issue: IssueReference | None


class NativeDispatch(Protocol):
    @property
    def instance_id(self) -> str:
        """Stable configured identity of the adapter's fixed native origin."""

    def lookup(self, command: DispatchCommand, correlation: str) -> IssueReference | None:
        """Read and verify the original Issue or an exact, trusted correlation.

        Return None only after a complete lookup found no match. Raise on
        access failure, partial results, ambiguity or untrusted evidence.
        """

    def check_create(self, command: DispatchCommand) -> None:
        """Read-only recheck of current authority, scope, coordinator and workflow."""

    def create_issue(self, command: DispatchCommand, correlation: str) -> IssueReference:
        """One native POST with atomic correlation, followed by verified readback.

        Raise if write or readback is inconclusive. The transport must disable
        automatic write retries. This method runs only after a durable claim.
        """


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class DeliveryLedger:
    """Local SQLite receipt ledger. Each call uses its own connection."""

    def __init__(self, path: str | Path) -> None:
        if str(path) == ":memory:":
            raise ValueError("delivery requires a durable SQLite path")
        self.path = Path(path).absolute()
        with closing(self._connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS delivery_requests (
                    principal TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    correlation TEXT NOT NULL UNIQUE,
                    instance_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('accepted', 'unknown', 'confirmed')),
                    issue_id TEXT,
                    command_json TEXT,
                    PRIMARY KEY (principal, request_id),
                    CHECK ((state = 'confirmed') = (issue_id IS NOT NULL)),
                    CHECK ((state = 'confirmed') = (command_json IS NULL))
                )
            """)
            db.execute("""
                CREATE INDEX IF NOT EXISTS delivery_pending
                ON delivery_requests (principal, state, request_id)
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS delivery_mailbox (
                    principal TEXT NOT NULL, request_id TEXT NOT NULL,
                    project_id TEXT NOT NULL, job_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, recipient TEXT NOT NULL,
                    PRIMARY KEY (principal, request_id), UNIQUE (job_id)
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _read(db: sqlite3.Connection, principal: str, request_id: str) -> sqlite3.Row | None:
        return db.execute("""
            SELECT * FROM delivery_requests WHERE principal = ? AND request_id = ?
        """, (principal, request_id)).fetchone()

    @staticmethod
    def _result(row: sqlite3.Row) -> DeliveryResult:
        instance_id, workspace_id, project_id = row["instance_id"], row["workspace_id"], row["project_id"]
        issue_id = row["issue_id"]
        issue = IssueReference(instance_id, workspace_id, project_id, issue_id) if issue_id is not None else None
        return DeliveryResult(row["state"], row["correlation"], instance_id, workspace_id, project_id, issue)

    def get(self, principal: str, request_id: str) -> DeliveryResult | None:
        """Read the historical receipt within the trusted principal's namespace."""
        with closing(self._connect()) as db:
            row = self._read(db, principal, request_id)
        return None if row is None else self._result(row)

    def list_pending(
        self, principal: str, *, state: Literal["accepted", "unknown"] = "accepted",
        after_request_id: str = "", limit: int = 50,
    ) -> tuple[str, ...]:
        """List IDs for one principal in ascending order, after the exclusive cursor."""
        if state not in ("accepted", "unknown") or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("pending state required and limit must be an integer between 1 and 100")
        with closing(self._connect()) as db:
            rows = db.execute("""
                SELECT request_id FROM delivery_requests
                WHERE principal = ? AND request_id > ? AND state = ?
                ORDER BY request_id LIMIT ?
            """, (principal, after_request_id, state, limit))
            return tuple(row["request_id"] for row in rows)

    def get_command(self, principal: str, request_id: str) -> DispatchCommand | None:
        """Load a pending command by its original key for trusted server-side recovery."""
        with closing(self._connect()) as db:
            row = self._read(db, principal, request_id)
        if row is None or row["command_json"] is None:
            return None
        data = json.loads(row["command_json"])
        if data["new_issue"] is not None:
            data["new_issue"] = NewIssue(**data["new_issue"])
        return DispatchCommand(**data)

    def accept(self, principal: str, request_id: str, command: DispatchCommand) -> DeliveryResult:
        """Persist intent identity before sending. Equivalent requests reuse the receipt."""
        if not principal.strip() or not request_id.strip():
            raise ValueError("authenticated principal and stable request ID are required")
        fields = asdict(command)
        if command.mailbox_payload_hash is None:
            # Preserve receipt fingerprints written before verified Mailbox links were added.
            del fields["mailbox_payload_hash"], fields["mailbox_recipient"]
        command_json = _canonical_json(fields)
        input_hash = hashlib.sha256(("dispatch-issue-v1:" + command_json).encode("utf-8")).hexdigest()
        request_key = _canonical_json([principal, request_id]).encode("utf-8")
        correlation = "mcp-dispatch-v1:" + hashlib.sha256(request_key).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute("""
                INSERT INTO delivery_requests (
                    principal, request_id, input_hash, correlation, instance_id,
                    workspace_id, project_id, state, command_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', ?)
                ON CONFLICT (principal, request_id) DO NOTHING
            """, (
                principal, request_id, input_hash, correlation, command.instance_id,
                command.workspace_id, command.project_id, command_json,
            ))
            row = self._read(db, principal, request_id)
            if row["input_hash"] != input_hash:
                raise RequestConflict("request ID already used for different command input")
            if command.mailbox_payload_hash is not None:
                db.execute("""
                    INSERT INTO delivery_mailbox VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                """, (principal, request_id, command.mailbox_project_id, command.mailbox_job_id,
                      command.mailbox_payload_hash, command.mailbox_recipient))
                binding = db.execute("""
                    SELECT job_id FROM delivery_mailbox WHERE principal = ? AND request_id = ?
                """, (principal, request_id)).fetchone()
                if binding is None or binding["job_id"] != command.mailbox_job_id:
                    raise RequestConflict("original Mailbox job already has a dispatch")
        return self._result(row)

    def mailbox_link(self, principal: str, request_id: str) -> dict | None:
        """Read the verified return route even after the transient command has been cleared."""
        with closing(self._connect()) as db:
            row = db.execute("""
                SELECT project_id, job_id, payload_hash, recipient FROM delivery_mailbox
                WHERE principal = ? AND request_id = ?
            """, (principal, request_id)).fetchone()
        return dict(row) if row is not None else None

    def _confirm(
        self, principal: str, request_id: str, command: DispatchCommand, issue: IssueReference
    ) -> DeliveryResult:
        try:
            issue_id = str(UUID(issue.issue_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise UnverifiedIssue("native Issue UUID is invalid") from exc
        if (issue.instance_id, issue.workspace_id, issue.project_id) != (
            command.instance_id, command.workspace_id, command.project_id
        ):
            raise UnverifiedIssue("native Issue does not match the requested instance, workspace and project")
        if command.original_issue_id is not None and issue_id != command.original_issue_id:
            raise UnverifiedIssue("native Issue does not match the requested original")
        with closing(self._connect()) as db, db:
            db.execute("""
                UPDATE delivery_requests SET state = 'confirmed', issue_id = ?, command_json = NULL
                WHERE principal = ? AND request_id = ? AND issue_id IS NULL
            """, (issue_id, principal, request_id))
            row = self._read(db, principal, request_id)
            if row["issue_id"] != issue_id:
                raise UnverifiedIssue("native evidence conflicts with an existing receipt")
        return self._result(row)

    def deliver(
        self, principal: str, request_id: str, command: DispatchCommand, native: NativeDispatch
    ) -> DeliveryResult:
        """Resume an accepted intent or reconcile a possible send using native reads.

        The caller authenticates and authorizes before invoking this method.
        Adapter errors propagate. Once claimed, an inconclusive failure leaves
        an unknown result available via get() and future read-only reconciliation.
        """
        current = self.accept(principal, request_id, command)
        if native.instance_id != command.instance_id:
            raise UnverifiedIssue("native adapter does not match the requested instance")
        if current.state == "confirmed":
            return current

        issue = native.lookup(command, current.correlation)
        if issue is not None:
            return self._confirm(principal, request_id, command, issue)
        if command.original_issue_id is not None:
            raise UnverifiedIssue("the original Issue could not be verified")
        if current.state == "unknown":
            return current

        native.check_create(command)
        with closing(self._connect()) as db, db:
            claim = db.execute("""
                UPDATE delivery_requests SET state = 'unknown'
                WHERE principal = ? AND request_id = ? AND state = 'accepted'
            """, (principal, request_id)).rowcount
            row = self._read(db, principal, request_id)
        if claim == 0:
            return self._result(row)

        issue = native.create_issue(command, current.correlation)
        return self._confirm(principal, request_id, command, issue)
