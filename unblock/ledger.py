"""Durably claim one coordinator notification per registered checkpoint."""

from collections.abc import Callable
from contextlib import closing
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import UUID


class NotificationNotSent(ValueError):
    """The current claim was stopped by a known pre-POST appointment check."""


def _receipt_json(
    callback: Callable[[str], dict | None], marker: str, action: str,
) -> tuple[str | None, str | None]:
    try:
        receipt = callback(marker)
    except Exception as exc:
        if action == "send" and isinstance(exc, NotificationNotSent):
            raise
        # The transport may have applied the request before reporting failure.
        return None, f"{action}_failed"
    if receipt is None:
        return None, None
    if (not isinstance(receipt, dict) or receipt.get("marker") != marker
            or receipt.get("state") != "started"):
        return None, f"{action}_receipt_invalid"
    try:
        for field in ("wakeup_id", "run_id"):
            value = receipt.get(field)
            if not isinstance(value, str) or str(UUID(value)) != value.lower():
                return None, f"{action}_receipt_invalid"
        started = receipt.get("started_at")
        if (not isinstance(started, str) or "T" not in started
                or datetime.fromisoformat(started).utcoffset() is None):
            return None, f"{action}_receipt_invalid"
        return json.dumps(receipt, allow_nan=False), None
    except (TypeError, ValueError, OverflowError, RecursionError):
        return None, f"{action}_receipt_invalid"


def reconcile(
    db_path: str | os.PathLike[str],
    scope_key: str,
    checkpoint_id: str,
    send: Callable[[str], dict | None],
    lookup: Callable[[str], dict | None],
) -> dict:
    """Send once after claiming, or read back the existing intent by exact marker."""
    return _reconcile(db_path, scope_key, checkpoint_id, lookup, send)


def reconcile_existing(
    db_path: str | os.PathLike[str],
    scope_key: str,
    checkpoint_id: str,
    lookup: Callable[[str], dict | None],
) -> dict:
    """Read back an existing intent without claiming or sending a notification."""
    return _reconcile(db_path, scope_key, checkpoint_id, lookup, None)


def _reconcile(
    db_path: str | os.PathLike[str],
    scope_key: str,
    checkpoint_id: str,
    lookup: Callable[[str], dict | None],
    send: Callable[[str], dict | None] | None,
) -> dict:
    path = os.fspath(db_path)
    if not isinstance(path, str) or path in ("", ":memory:"):
        raise ValueError("ledger requires a persistent SQLite file")
    if not isinstance(scope_key, str) or not scope_key.strip():
        raise ValueError("scope_key must be a non-empty registration key")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("checkpoint_id must be a non-empty logical checkpoint")

    key = (scope_key, checkpoint_id)
    database = Path(path).absolute()
    if send is None:
        try:
            database.stat()
        except FileNotFoundError:
            return {"status": "not_found", "marker": None, "receipt": None}

    mode = "rw" if send is None else "rwc"
    with closing(sqlite3.connect(f"{database.as_uri()}?mode={mode}", uri=True)) as db:
        db.execute("PRAGMA synchronous = FULL")
        claimed = False
        if send is not None:
            db.execute("""
                CREATE TABLE IF NOT EXISTS unblock_notifications (
                    scope_key TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    marker TEXT NOT NULL UNIQUE,
                    receipt_json TEXT,
                    PRIMARY KEY (scope_key, checkpoint_id)
                )
            """)
            encoded_key = json.dumps(key, separators=(",", ":")).encode("ascii")
            marker = f"unblock.v1:{hashlib.sha256(encoded_key).hexdigest()}"
            with db:
                claimed = db.execute("""
                    INSERT INTO unblock_notifications (scope_key, checkpoint_id, marker)
                    VALUES (?, ?, ?)
                    ON CONFLICT (scope_key, checkpoint_id) DO NOTHING
                """, (*key, marker)).rowcount == 1
        elif db.execute("""
            SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'unblock_notifications'
        """).fetchone() is None:
            return {"status": "not_found", "marker": None, "receipt": None}

        # A committed row consumes the only send attempt, including after a crash.
        read_intent = """
            SELECT marker, receipt_json FROM unblock_notifications
            WHERE scope_key = ? AND checkpoint_id = ?
        """
        intent = db.execute(read_intent, key).fetchone()
        if intent is None:
            return {"status": "not_found", "marker": None, "receipt": None}
        marker, stored = intent
        reason = None
        if stored is None:
            receipt = None
            if claimed and send is not None:
                try:
                    receipt, reason = _receipt_json(send, marker, "send")
                except NotificationNotSent as exc:
                    # Only this INSERT winner can attest its call stopped before POST.
                    with db:
                        released = db.execute("""
                            DELETE FROM unblock_notifications
                            WHERE scope_key = ? AND checkpoint_id = ? AND marker = ?
                              AND receipt_json IS NULL
                        """, (*key, marker)).rowcount
                    if released:
                        return {"status": "deferred", "marker": marker, "receipt": None, "reason": str(exc)}
            if receipt is None:
                receipt, lookup_reason = _receipt_json(lookup, marker, "lookup")
                reason = lookup_reason or reason
            if receipt is not None:
                with db:
                    db.execute("""
                        UPDATE unblock_notifications SET receipt_json = ?
                        WHERE scope_key = ? AND checkpoint_id = ? AND receipt_json IS NULL
                    """, (receipt, *key))
            intent = db.execute(read_intent, key).fetchone()
            if intent is None:
                # The claim holder proved it stopped before POST while we were looking up.
                return {"status": "not_found", "marker": None, "receipt": None}
            _, stored = intent

    if stored is None:
        return {"status": "unknown", "marker": marker, "receipt": None,
                "reason": reason or "receipt_pending"}
    return {"status": "confirmed", "marker": marker, "receipt": json.loads(stored)}
