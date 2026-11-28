"""Maintain one existing central Hindsight document from a squad leader's Multica Run."""
import argparse
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from uuid import NAMESPACE_URL, UUID, uuid5

BANK = "multica-4-dot"
WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
ROUTES = {
    "dev": ("1ea4aac9-ebdf-407e-9696-b471cb89d9bd", "dev-squad-cross-project-engineering-reuse"),
    "qa": ("a6e2a426-e1d8-4e2d-ae90-118567d5f536", "quality-squad-review-methods"),
}
PREFIX = "/note\n\nsquad-index-update/v1 "


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def scope(team, issue, agent, task, get):
    squad, doc = ROUTES[team]
    appointment = get("squad", "get", squad)
    require(appointment.get("id") == squad and appointment.get("workspace_id") == WORKSPACE
            and appointment.get("leader_id") == agent, "Current squad leader required.")
    card = get("issue", "get", issue)
    require(card.get("id") == issue and card.get("workspace_id") == WORKSPACE
            and card.get("project_id"), "Project-bound original Issue required.")
    runs = get("issue", "runs", issue, "--active")
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


async def maintain(team, issue, note, agent, task, get, upstream):
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
    rows = get("issue", "comment", "list", issue)
    signed = next((r for r in rows if r.get("id") == note), {})
    source_run = signed.get("source_task_id")
    require(source_run, "A native leader Run receipt is required.")
    if source_run != task:
        # A later Run may resume the same signed request after a lost reply.
        prior = get("issue", "runs", issue)
        require(any(r.get("id") == source_run and r.get("agent_id") == agent and
                    r.get("issue_id") == issue and r.get("workspace_id") == WORKSPACE for r in prior),
                "The prior signer must be the same current leader on this Issue.")
    data = intent(rows, issue, note, agent, source_run, team)
    delta = data["addition"].strip()
    op = str(uuid5(NAMESPACE_URL, f"{WORKSPACE}/{doc}/{note}"))

    async def operation():
        state = await call("get_operation", {"bank_id": BANK, "operation_id": op})
        require(state.get("operation_id") == op, "Operation identity mismatch.")
        return state.get("status")

    state = await operation()
    if state == "not_found":
        if delta in before:
            return dict(target, status="already_covered", sha256=digest(before))
        require(digest(before) == data["base_sha256"], "Document changed; read it and compare the proposed addition.")
        merged = before + "\n" + delta
        metadata = dict(old.get("document_metadata") or {})
        metadata.update(content_sha256=digest(merged), last_source_ref=f"{issue}#comment-{note}",
                        last_index_commit=data["commit"], last_leader_run=source_run)
        # The native append engine preserves the stored base on concurrent submissions.
        payload = dict(target, operation_id=op, update_mode="append", content=delta, metadata=metadata,
                       tags=old.get("tags") or [])
        context = (old.get("retain_params") or {}).get("context")
        if context:
            payload["context"] = context
        confirm()
        receipt = await call("retain", payload)
        require(receipt.get("operation_id") == op, "Unknown submission; reconcile " + op)
        state = await operation()
    for _ in range(20):
        if state == "completed":
            actual = await read()
            body = actual["original_text"]
            require(delta in body and body.startswith(before) and actual["document_metadata"]["content_sha256"] == digest(body),
                    "Content or metadata changed; reconcile the completed operation without resubmitting.")
            return dict(target, status=state, operation_id=op, sha256=digest(body))
        require(state in {"accepted", "pending", "processing", "running"}, "Reconcile " + op + " (" + str(state) + ")")
        await asyncio.sleep(2)
        state = await operation()
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
    cli = Path(env["MULTICA_CLI_PATH"])
    require(cli.is_absolute() and cli.is_file(), "The injected Multica CLI is required.")

    def get(*args):
        result = subprocess.run([str(cli), "--workspace-id", WORKSPACE, *args, "--output", "json"],
                                capture_output=True, timeout=20)
        require(result.returncode == 0, "Multica CLI read failed: " + " ".join(args[:2]))
        return json.loads(result.stdout.decode("utf-8-sig"))

    client = runpy.run_path(str(Path.home() / ".kimi-code/hindsight/project_memory.py"))
    result = asyncio.run(maintain(args.team, args.issue, args.note, agent, task, get, client["upstream_call"]))
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        sys.exit(str(exc))
