"""Read the active workspace designation using the coordinator host's restricted SSH identity."""

from datetime import datetime, timezone
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from uuid import UUID


class AppointmentUnavailable(ValueError):
    """The authority could not establish one current appointment."""


def _uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _unique_fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate appointment field")
    return result


def _validate_record(record, instance, workspace):
    if not isinstance(record, dict) or set(record) != {
        "instance_id", "workspace_id", "coordinator_id", "generation", "confirmed_since"
    }:
        raise ValueError("appointment fields")
    if (record["instance_id"] != instance or record["workspace_id"] != workspace
            or not _uuid(record["coordinator_id"]) or not isinstance(record["generation"], str)
            or not re.fullmatch(r"[a-f0-9]{32}", record["generation"])):
        raise ValueError("appointment scope")
    since = datetime.fromisoformat(record["confirmed_since"])
    if since.utcoffset() is None or since > datetime.now(timezone.utc):
        raise ValueError("appointment watermark")
    return record


def read_appointment(config_path, instance, workspace):
    if (not isinstance(config_path, str) or not Path(config_path).is_absolute()
            or not isinstance(instance, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", instance)
            or not _uuid(workspace)):
        raise AppointmentUnavailable("coordinator_appointment_unconfirmed")
    try:
        reply = subprocess.run(
            ["/usr/bin/ssh", "-F", config_path, "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
             "unblock-appointment", "read-appointment", instance, workspace],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=True,
        ).stdout
        if len(reply) > 2048:
            raise ValueError("oversize appointment")
        return _validate_record(json.loads(reply, object_pairs_hook=_unique_fields), instance, workspace)
    except (OSError, subprocess.SubprocessError, TypeError, ValueError, RecursionError, OverflowError):
        raise AppointmentUnavailable("coordinator_appointment_unconfirmed") from None


def bind_appointment(registration, record):
    """Materialize the role for this pass; independent project roles keep their original authority."""
    role = {
        "id": record["coordinator_id"], "name": "工作区现任协调员",
        "appointment_ref": f"multica-gateway:{record['instance_id']}/{record['workspace_id']}/{record['generation']}",
        "valid_from": record["confirmed_since"], "valid_until": None,
    }
    return {**registration, "coordinator_id": role["id"], "_live_appointment": record,
            "roles": {**registration.get("roles", {}), "coordinator": role}}


class AppointmentScan:
    """A cached designation may select candidate notes; only a live read can authorize a send."""

    def __init__(self, ledger_path=None):
        self.ledger = ledger_path
        self.observed = {}
        self.failed = set()

    def refresh(self, config, instance, workspace):
        key = (config, instance, workspace)
        if key in self.failed:
            raise AppointmentUnavailable("coordinator_appointment_unconfirmed")
        checked = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            record = read_appointment(*key)
        except AppointmentUnavailable:
            self.failed.add(key)
            raise
        if self.ledger:
            with closing(sqlite3.connect(self.ledger)) as db, db:
                db.execute("""CREATE TABLE IF NOT EXISTS unblock_appointment_cache (
                    source TEXT, instance_id TEXT, workspace_id TEXT, checked_at TEXT NOT NULL,
                    record TEXT NOT NULL, PRIMARY KEY(source, instance_id, workspace_id))""")
                db.execute("""INSERT INTO unblock_appointment_cache VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source, instance_id, workspace_id) DO UPDATE SET
                    checked_at=excluded.checked_at, record=excluded.record
                    WHERE excluded.checked_at >= unblock_appointment_cache.checked_at""",
                           (*key, checked, json.dumps(record, separators=(",", ":"))))
        self.observed[key] = record, checked, False
        return record

    def bind(self, reg):
        key = (reg["appointment_ssh_config"], reg["instance_id"], reg["workspace_id"])
        if key not in self.observed and self.ledger:
            with closing(sqlite3.connect(self.ledger)) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='unblock_appointment_cache'").fetchone()
                row = db.execute("""SELECT checked_at,record FROM unblock_appointment_cache
                    WHERE source=? AND instance_id=? AND workspace_id=?""", key).fetchone() if exists else None
            if row:
                try:
                    checked = datetime.fromisoformat(row[0])
                    if checked.utcoffset() is None or checked > datetime.now(timezone.utc):
                        raise ValueError("invalid cache observation time")
                    record = _validate_record(json.loads(row[1], object_pairs_hook=_unique_fields), *key[1:])
                    self.observed[key] = record, row[0], True
                except (ValueError, TypeError, OverflowError, RecursionError):
                    pass  # Fetch the authority when the scan cache is unusable.
        if key not in self.observed:
            self.refresh(*key)
        record, checked, cached = self.observed[key]
        return {**bind_appointment(reg, record), "_appointment_cached": cached, "_appointment_checked_at": checked}
