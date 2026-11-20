"""Poll registered Multica runs once. Task Mailbox is the only write destination."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
from http.client import HTTPConnection, HTTPException, HTTPSConnection
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit
from uuid import UUID

ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
TERMINAL = {"failed", "cancelled", "completed"}
BATCHES = "/observations/batches"


class Problem(Exception):
    """Diagnostic safe to send to the journal."""


class Conflict(Problem):
    """Mailbox has a different document with this ID."""


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def endpoint(value, *, mailbox):
    url = urlsplit(value)
    local = url.hostname == "localhost"
    if url.hostname and not local:
        try:
            local = ipaddress.ip_address(url.hostname).is_loopback
        except ValueError:
            pass
    if (not url.hostname or url.username is not None or url.password is not None or
            url.query or url.fragment or
            url.path.rstrip("/") != ("/mailbox/api/v1" if mailbox else "") or
            not (url.scheme == "https" or (not mailbox and local and url.scheme == "http"))):
        raise Problem("invalid endpoint (HTTPS required except for local Multica)")
    return value.rstrip("/")


def load_config(path):
    cfg = json.loads(path.read_bytes())
    scope_keys = {"multica_origin", "mailbox_api", "workspace_id", "project_id", "mailbox_project_id", "source_id"}
    if not isinstance(cfg, dict) or cfg.keys() != scope_keys | {"watches"}:
        raise Problem("invalid configuration fields")
    cfg["multica_origin"] = endpoint(cfg["multica_origin"], mailbox=False)
    cfg["mailbox_api"] = endpoint(cfg["mailbox_api"], mailbox=True)
    for key in ("workspace_id", "project_id"):
        cfg[key] = str(UUID(cfg[key]))
    for key in ("mailbox_project_id", "source_id"):
        if not ID.fullmatch(cfg[key]):
            raise Problem("invalid Mailbox source/project ID")
    if not isinstance(cfg["watches"], list):
        raise Problem("watches must be an array")
    seen = set()
    for watch in cfg["watches"]:
        required = {"issue_id", "run_id", "task_id"}
        if not isinstance(watch, dict) or not required <= watch.keys() <= required | {"job_id"}:
            raise Problem("invalid registration fields")
        for key in ("issue_id", "run_id"):
            watch[key] = str(UUID(watch[key]))
        if not ID.fullmatch(watch["task_id"]) or ("job_id" in watch and not ID.fullmatch(watch["job_id"])):
            raise Problem("invalid registered Mailbox ID")
        if watch["run_id"] in seen:
            raise Problem("duplicate Run registration")
        seen.add(watch["run_id"])
    return cfg


def credential(name):
    token = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / name).read_text().rstrip("\r\n")
    if not token or not token.isascii() or any(not 33 <= ord(c) <= 126 for c in token):
        raise Problem("invalid credential file")
    if name == "multica.token" and token.startswith("mat_"):
        raise Problem("a temporary Run token cannot be a service credential")
    return token


def request(url, headers, *, body=None, lookup=False, limit=1024 * 1024, timeout=10):
    target = urlsplit(url)
    connection = HTTPSConnection if target.scheme == "https" else HTTPConnection
    path = target.path + ("?" + target.query if target.query else "")
    # http.client does not follow redirects or retry a POST on transport failure.
    try:
        with closing(connection(target.hostname, target.port, timeout=timeout)) as conn:
            conn.request("POST" if body is not None else "GET", path, body=body, headers=headers)
            response = conn.getresponse()
            status = response.status
            if status != 200 and not (lookup and status == 404) and not (body is not None and status == 409):
                raise Problem(f"HTTP {status}")
            raw = response.read(limit + 1)
    except (OSError, HTTPException) as exc:
        raise Problem(f"transport failed ({type(exc).__name__})") from None
    if len(raw) > limit:
        raise Problem("response exceeds size limit")
    try:
        reply = json.loads(raw)
    except (ValueError, RecursionError):
        raise Problem(f"invalid JSON in HTTP {status}") from None
    if status == 200:
        if reply is None:
            raise Problem("unexpected JSON null")
        return reply
    error = reply.get("error") if isinstance(reply, dict) else None
    if isinstance(error, dict):
        if (lookup and status == 404 and error.get("code") == "NOT_FOUND" and
                error.get("message") == "Observation receipt not found" and error.get("retryable") is False and
                isinstance(reply.get("request_id"), str) and reply["request_id"]):
            return None
        if status == 409 and error.get("code") == "OBSERVATION_CONFLICT":
            raise Conflict("OBSERVATION_CONFLICT")
    raise Problem(f"unexpected HTTP {status} error envelope")


def observe(cfg, watch, headers):
    issue_path = "/api/issues/" + watch["issue_id"]
    issue_url = cfg["multica_origin"] + issue_path
    issue = request(issue_url, headers, limit=8 * 1024 * 1024)
    if (not isinstance(issue, dict) or issue.get("id") != watch["issue_id"] or
            issue.get("workspace_id") != cfg["workspace_id"] or issue.get("project_id") != cfg["project_id"]):
        raise Problem("Issue identity or scope mismatch")
    runs_path = issue_path + "/task-runs?scope=issue&view=timeline"
    runs = request(cfg["multica_origin"] + runs_path, headers, limit=8 * 1024 * 1024)
    if not isinstance(runs, list) or not all(isinstance(row, dict) for row in runs):
        raise Problem("invalid Run history")
    matches = [row for row in runs if row.get("id") == watch["run_id"]]
    if len(matches) != 1:
        raise Problem("registered Run missing or ambiguous")
    run = matches[0]
    if (run.get("issue_id") != watch["issue_id"] or run.get("workspace_id") != cfg["workspace_id"]
            or run.get("restricted", False) is not False):
        raise Problem("Run identity or scope mismatch")
    status = run.get("status")
    if not isinstance(status, str) or not status:
        raise Problem("invalid Run status")
    if status not in TERMINAL:
        return None
    completed = run.get("completed_at")
    if completed is not None:
        try:
            if datetime.fromisoformat(completed.replace("Z", "+00:00")).utcoffset() is None:
                raise ValueError
        except (ValueError, AttributeError, TypeError, OverflowError):
            raise Problem("invalid Run completion time") from None
    now = datetime.now(timezone.utc).isoformat()
    run_ref = runs_path + "#id=" + watch["run_id"]
    references = [
        ("multica_issue", f"{issue_path} (workspace_id={cfg['workspace_id']}, project_id={cfg['project_id']})"),
        ("multica_run", run_ref),
    ]
    if status == "failed" and (run.get("has_error") is True or run.get("error")):
        references.append(("multica_run_error", run_ref + "&field=error"))
    if "job_id" in watch:
        references.append(("registered_mailbox_job", "job:" + watch["job_id"]))
    evidence = [{"source_type": kind, "ref": ref, "authority": "native_observation", "observed_at": now}
                for kind, ref in references]
    # One terminal fact per registered Run. The batch also identifies its frozen body.
    identity = [cfg["source_id"], cfg["workspace_id"], cfg["project_id"], watch["issue_id"], watch["run_id"]]
    event = {"event_id": "run." + hashlib.sha256(encode(identity)).hexdigest(),
             "project_id": cfg["mailbox_project_id"], "entity_type": "task", "entity_id": watch["task_id"],
             "task_id": watch["task_id"], "run_id": watch["run_id"], "event_type": "activity",
             "observed_at": now, "occurred_at": completed, "payload": {"reported_status": "Multica Run " + status},
             "evidence": evidence}
    batch = {"schema_version": 1, "source_id": cfg["source_id"], "events": [event]}
    batch["batch_id"] = "batch." + hashlib.sha256(encode(batch)).hexdigest()
    return encode(batch)


def deliver(api, headers, original):
    batch = json.loads(original)
    # Allow the writer to finish its bounded PostgreSQL reconnect/replay window.
    receipt = request(api + BATCHES + "/" + batch["batch_id"], headers, lookup=True, timeout=65)
    if receipt is None:
        receipt = request(api + BATCHES, headers, body=original, timeout=65)
    event_id = batch["events"][0]["event_id"]
    if (not isinstance(receipt, dict) or receipt.get("persisted") is not True
            or receipt.get("source_id") != batch["source_id"] or receipt.get("batch_id") != batch["batch_id"]
            or (receipt.get("accepted_event_ids"), receipt.get("duplicate_event_ids")) not in
               (([event_id], []), ([], [event_id]))
            or not isinstance(receipt.get("watermark"), str)
            or not re.fullmatch(r"0|[1-9][0-9]{0,18}", receipt["watermark"])):
        raise Problem("receipt does not confirm the exact batch and event")
    return receipt


def cycle(db, cfg, multica_headers, mailbox_headers):
    db.execute("CREATE TABLE IF NOT EXISTS scope (id INTEGER PRIMARY KEY CHECK(id=1), binding BLOB NOT NULL)")
    db.execute("""CREATE TABLE IF NOT EXISTS outbox (
        run_id TEXT PRIMARY KEY, registration BLOB NOT NULL, original BLOB NOT NULL,
        receipt BLOB, conflict TEXT)""")
    binding = encode({key: value for key, value in cfg.items() if key != "watches"})
    with db:
        db.execute("INSERT OR IGNORE INTO scope VALUES(1, ?)", (binding,))
        if db.execute("SELECT binding FROM scope WHERE id=1").fetchone()[0] != binding:
            raise Problem("database belongs to a different source, endpoint or project")
    errors = 0
    for watch in cfg["watches"]:
        run_id = watch["run_id"]
        stage = "Multica"
        try:
            row = db.execute("SELECT registration, original, receipt, conflict FROM outbox WHERE run_id=?",
                             (run_id,)).fetchone()
            if row is None:
                original = observe(cfg, watch, multica_headers)
                if original is None:
                    continue
                with db:
                    db.execute("INSERT INTO outbox(run_id, registration, original) VALUES(?,?,?)",
                               (run_id, encode(watch), original))
            else:
                registered, original, receipt, conflict = row
                if registered != encode(watch):
                    raise Problem("registration differs from frozen observation")
                if conflict:
                    raise Problem("quarantined Mailbox conflict requires reconciliation")
                if receipt is not None:
                    continue
            stage = "Mailbox"
            receipt = deliver(cfg["mailbox_api"], mailbox_headers, original)
            with db:
                db.execute("UPDATE outbox SET receipt=? WHERE run_id=?", (encode(receipt), run_id))
            print(f"confirmed run={run_id} batch={receipt['batch_id']} watermark={receipt['watermark']}")
        except Problem as exc:
            if isinstance(exc, Conflict):
                with db:
                    db.execute("UPDATE outbox SET conflict=? WHERE run_id=?", (str(exc), run_id))
            print(f"{stage} run={run_id} {exc}", file=sys.stderr)
            errors += 1
    return int(bool(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    cfg = load_config(args.config)
    reader = {"Authorization": "Bearer " + credential("multica.token"), "X-Workspace-ID": cfg["workspace_id"]}
    sender = {"Authorization": "Bearer " + credential("mailbox.token"), "Content-Type": "application/json"}
    # A concurrent manual invocation must not race a timer through capture/confirmation.
    with Path(str(args.database) + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with closing(sqlite3.connect(args.database)) as db:
            return cycle(db, cfg, reader, sender)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Problem as exc:
        sys.exit(str(exc))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error) as exc:
        sys.exit(f"reporter setup/state failure ({type(exc).__name__})")
