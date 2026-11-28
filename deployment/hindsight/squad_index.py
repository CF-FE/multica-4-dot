"""Maintain one existing central Hindsight document from a squad leader's Multica Run."""
import argparse
import asyncio
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import sqlite3
import sys
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from uuid import NAMESPACE_URL, UUID, uuid5

BANK = "multica-4-dot"
WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
ORIGIN = "http://10.207.56.3:8080"
ROUTES = {
    "dev": ("1ea4aac9-ebdf-407e-9696-b471cb89d9bd", "dev-squad-cross-project-engineering-reuse"),
    "qa": ("a6e2a426-e1d8-4e2d-ae90-118567d5f536", "quality-squad-review-methods"),
}
PREFIX = "/note\n\nsquad-index-update/v1 "


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def scope(team, issue, agent, task, get):
    squad, doc = ROUTES[team]
    appointment = get("squads/" + squad)
    require(appointment.get("id") == squad and appointment.get("workspace_id") == WORKSPACE
            and appointment.get("leader_id") == agent, "Current squad leader required.")
    card = get("issues/" + issue)
    require(card.get("id") == issue and card.get("workspace_id") == WORKSPACE
            and card.get("project_id"), "Project-bound original Issue required.")
    runs = get("issues/" + issue + "/task-runs?scope=issue&view=timeline")
    require(any(r.get("id") == task and r.get("agent_id") == agent and r.get("issue_id") == issue
                and r.get("workspace_id") == WORKSPACE and r.get("status") == "running" for r in runs),
            "No matching active Run on this Issue.")
    return doc


def intent(rows, issue, note, agent, task, team):
    row = next((r for r in rows if r.get("id") == note), {})
    require(row.get("issue_id") == issue and row.get("author_type") == "agent"
            and row.get("author_id") == agent and row.get("source_task_id") == task,
            "The server-attributed note must belong to this leader, Run and Issue.")
    body = row["content"].replace("\r\n", "\n")
    prefix = PREFIX + team + "\n"
    require(body.startswith(prefix), "Expected an explicit squad-index-update/v1 note.")
    data = json.loads(body[len(prefix):])
    require(isinstance(data, dict) and set(data) == {"base_sha256", "commit", "addition"},
            "Expected only base_sha256, commit and addition.")
    require(all(isinstance(x, str) for x in data.values())
            and re.fullmatch("[0-9a-f]{64}", data["base_sha256"])
            and re.fullmatch("[0-9a-f]{40}", data["commit"]) and data["addition"].strip(), "Invalid receipt fields.")
    return data


async def maintain(team, issue, note, agent, task, get, upstream, ledger):
    def confirm():
        return scope(team, issue, agent, task, get)

    doc = confirm()
    target = {"bank_id": BANK, "document_id": doc}

    async def call(tool, args):
        data, failed = await upstream(tool, args, 35)
        require(not failed and isinstance(data, dict) and not data.get("error"), "Upstream failed: " + tool)
        return data

    async def read():
        d = await call("get_document", target)
        require(d.get("id") == doc and d.get("bank_id") == BANK and isinstance(d.get("original_text"), str),
                "Existing canonical document required.")
        return d

    old = await read()
    before = old["original_text"]
    if note is None:
        return dict(target, original_text=before, sha256=digest(before))
    data = intent(get("issues/" + issue + "/comments"), issue, note, agent, task, team)
    delta = data["addition"].strip()
    op = str(uuid5(NAMESPACE_URL, f"{WORKSPACE}/{doc}/{note}"))
    # Reserve this document before submission. An unknown response keeps the reservation.
    # Other leader Runs may only release it after native completion and exact readback.
    with closing(sqlite3.connect(ledger, timeout=15, isolation_level=None)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS pending (doc TEXT PRIMARY KEY, op TEXT NOT NULL, sha TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT op,sha FROM pending WHERE doc=?", (doc,)).fetchone()
        if previous:
            status = await call("get_operation", {"bank_id": BANK, "operation_id": previous[0]})
            require(status.get("operation_id") == previous[0] and status.get("status") == "completed",
                    "Pending operation requires reconciliation: " + previous[0])
            old = await read()
            before = old["original_text"]
            require(digest(before) == previous[1], "Pending document digest requires reconciliation.")
            db.execute("DELETE FROM pending WHERE doc=?", (doc,))
        else:
            old = await read()
            before = old["original_text"]
        if delta in before:
            db.commit()
            return dict(target, status="already_covered", sha256=digest(before))
        require(digest(before) == data["base_sha256"], "Document changed; read it and compare the proposed addition.")
        merged = before + "\n\n" + delta
        expected = digest(merged)
        metadata = dict(old.get("document_metadata") or {})
        metadata.update(content_sha256=expected, last_source_ref=f"{issue}#comment-{note}",
                        last_index_commit=data["commit"], last_leader_run=task)
        payload = dict(target, operation_id=op, content=merged, metadata=metadata, tags=old.get("tags") or [])
        context = (old.get("retain_params") or {}).get("context")
        if context:
            payload["context"] = context
        confirm()
        db.execute("INSERT INTO pending VALUES(?,?,?)", (doc, op, expected))
        db.commit()
        submitted = await call("retain", payload)
        require(submitted.get("operation_id") == op, "Unknown submission; reconcile " + op)
        for _ in range(20):
            status = await call("get_operation", {"bank_id": BANK, "operation_id": op})
            require(status.get("operation_id") == op, "Operation identity mismatch.")
            if status.get("status") == "completed":
                actual = await read()
                require(actual["original_text"] == merged and actual["document_metadata"]["content_sha256"] == expected,
                        "Completed operation did not read back as submitted.")
                db.execute("DELETE FROM pending WHERE doc=? AND op=?", (doc, op))
                return dict(target, status="completed", operation_id=op, sha256=expected)
            require(status.get("status") in {"accepted", "pending", "processing", "running"}, "Reconcile " + op)
            await asyncio.sleep(2)
        return dict(target, status="pending", operation_id=op)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("team", choices=ROUTES)
    parser.add_argument("issue", type=lambda v: str(UUID(v)))
    parser.add_argument("--note", type=lambda v: str(UUID(v)), help="Apply the leader's explicit note; otherwise read.")
    args = parser.parse_args()
    env = os.environ
    require(env.get("MULTICA_WORKSPACE_ID") == WORKSPACE and env.get("MULTICA_TOKEN", "").startswith("mat_"),
            "Use the workspace's injected Run identity.")
    agent, task = (str(UUID(env[k])) for k in ("MULTICA_AGENT_ID", "MULTICA_TASK_ID"))
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(path):
        req = Request(ORIGIN + "/api/" + path, headers={"Authorization": "Bearer " + env["MULTICA_TOKEN"],
                                                       "X-Workspace-ID": WORKSPACE})
        with opener.open(req, timeout=10) as response:
            return json.load(response)

    client = runpy.run_path(str(Path.home() / ".kimi-code/hindsight/project_memory.py"))
    ledger = Path(__file__).resolve().with_name("squad-index-pending.sqlite")
    result = asyncio.run(maintain(args.team, args.issue, args.note, agent, task, get, client["upstream_call"], ledger))
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        sys.exit(str(exc))
