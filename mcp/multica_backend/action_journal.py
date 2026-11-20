"""Local single-attempt claims for native writes without a universal idempotency key."""

from contextlib import closing
import hashlib
import json
import sqlite3


class ActionConflict(ValueError):
    """The same authenticated principal used this request ID for other input."""


class ActionJournal:
    def __init__(self, state_path):
        self._path = state_path
        with closing(self._connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS native_operation_requests (
                    principal TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    result TEXT,
                    PRIMARY KEY (principal, request_id)
                )
            """)

    def _connect(self):
        return sqlite3.connect(self._path, timeout=10)

    @staticmethod
    def fingerprint(instance_id, action, arguments):
        frozen = json.dumps([instance_id, action, arguments], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(frozen.encode("utf-8")).hexdigest()

    @staticmethod
    def _get(db, principal, request_id, fingerprint):
        row = db.execute("""
            SELECT fingerprint, result FROM native_operation_requests WHERE principal = ? AND request_id = ?
        """, (principal, request_id)).fetchone()
        if row is None:
            return None
        if row[0] != fingerprint:
            raise ActionConflict("native operation request ID already used")
        return json.loads(row[1]) if row[1] is not None else {"status": "unknown", "reason": "unconfirmed_write"}

    def get(self, principal, request_id, fingerprint):
        with closing(self._connect()) as db:
            return self._get(db, principal, request_id, fingerprint)

    def claim(self, principal, request_id, fingerprint):
        """Return None only to the winner after durably recording an unknown outcome."""
        with closing(self._connect()) as db, db:
            inserted = db.execute("""
                INSERT INTO native_operation_requests (principal, request_id, fingerprint)
                VALUES (?, ?, ?) ON CONFLICT (principal, request_id) DO NOTHING
            """, (principal, request_id, fingerprint)).rowcount
            if inserted:
                return None
            return self._get(db, principal, request_id, fingerprint)

    def finish(self, principal, request_id, fingerprint, result):
        with closing(self._connect()) as db, db:
            updated = db.execute("""
                UPDATE native_operation_requests SET result = ?
                WHERE principal = ? AND request_id = ? AND fingerprint = ? AND result IS NULL
            """, (json.dumps(result, separators=(",", ":")), principal, request_id, fingerprint)).rowcount
            if updated != 1:
                raise sqlite3.OperationalError("native operation claim missing")
