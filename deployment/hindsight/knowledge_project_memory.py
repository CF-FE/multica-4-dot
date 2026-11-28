"""The win-work knowledge manager's task-scoped Hindsight stdio server."""
import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler, Request
from uuid import UUID

ROLE = "7fe827c7-11ad-4afa-ba03-9f883deb16c4"
WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
WORKSPACE_DIR = "cloud-work-bb5c5700b1af"
ORIGIN = "http://10.207.56.3:8080"
CROSS_READ = {"multica-4-dot", "cf-fe-herdr-4-codexcloud"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


@dataclass(frozen=True)
class Scope:
    issue: str
    project: str
    bank: str


def current_scope():
    env = os.environ
    if env.get("MULTICA_WORKSPACE_ID") != WORKSPACE or env.get("MULTICA_AGENT_ID") != ROLE:
        raise ValueError("Knowledge manager task identity required.")
    token = env.get("MULTICA_TOKEN", "")
    if not token.startswith("mat_"):
        raise ValueError("An active Multica Run token is required.")
    task = str(UUID(env["MULTICA_TASK_ID"]))
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(path):
        request = Request(ORIGIN + "/api/" + path,
                          headers={"Authorization": "Bearer " + token, "X-Workspace-ID": WORKSPACE})
        with opener.open(request, timeout=8) as response:
            return json.load(response)

    # A project may supply a custom workdir. The native task owns its Issue link.
    runs = get("agents/" + ROLE + "/tasks?status=running&limit=100")
    run = next((r for r in runs if r["id"] == task and r.get("agent_id") == ROLE
                and r.get("workspace_id") == WORKSPACE and r.get("status") == "running"), None)
    if run is None:
        raise ValueError("The current Run is not active for this role and workspace.")
    issue = str(UUID(run["issue_id"]))
    card = get("issues/" + issue)
    if card["id"] != issue or card["workspace_id"] != WORKSPACE:
        raise ValueError("Original Issue and active Run do not match.")
    project = card["project_id"]
    path = Path.home() / ".multica/integrations/hindsight/omp-project-banks.json"
    routes = json.loads(path.read_text("utf-8-sig"))["multicaWorkspaces"][WORKSPACE_DIR]
    bank = routes.get(project)
    if not bank or bank.lower() == "default" or list(routes.values()).count(bank) != 1:
        raise ValueError("Original Issue has no unique registered project bank.")
    return Scope(issue, project, bank)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def bind(server, resolve, upstream):
    # One private stdio process per session. Recheck native Issue/Run on each call.
    searches = set()

    async def check(bank, *, write=False):
        scope = await asyncio.to_thread(resolve)
        if bank != scope.bank and (write or bank not in CROSS_READ):
            raise ValueError("This bank is outside the permitted scope for this Issue.")
        return scope

    async def call(tool, args):
        data, failed = await upstream(tool, args, 30)
        if failed or not isinstance(data, dict) or data.get("error"):
            raise ValueError(str(data.get("error", "Hindsight operation failed"))[:400]
                             if isinstance(data, dict) else "Invalid Hindsight response")
        return data

    @server.tool
    async def recall(bank_id: str, query: str, max_tokens: int = 1600) -> dict:
        """Search by original Issue, topic and source before retaining. Cross-bank results are read-only."""
        scope = await check(bank_id)
        result = await call("recall", {"bank_id": bank_id, "query": query,
                                       "max_tokens": max_tokens, "budget": "low"})
        if bank_id == scope.bank and query.strip() and isinstance(result.get("results"), list):
            searches.add(scope)
        return result

    @server.tool
    async def get_document(bank_id: str, document_id: str) -> dict:
        """Read the original by stable ID. Use original_sha256 for an append."""
        await check(bank_id)
        data = await call("get_document", {"bank_id": bank_id, "document_id": document_id})
        if data.get("id") != document_id or data.get("bank_id") != bank_id:
            raise ValueError("Document readback identity mismatch.")
        return dict(data, original_sha256=digest(data["original_text"]))

    @server.tool
    async def get_operation(bank_id: str, operation_id: str) -> dict:
        """Reconcile an accepted or uncertain retain by its original operation UUID."""
        await check(bank_id, write=True)
        return await call("get_operation", {"bank_id": bank_id, "operation_id": str(UUID(operation_id))})

    @server.tool
    async def retain(bank_id: str, document_id: str, expected_sha256: str, addition: str,
                     source_ref: str, operation_id: str) -> dict:
        """After recall, append only sourced, redacted omissions to the canonical document.
        For a truly new topic use expected_sha256='new'. Reuse the same operation UUID on uncertainty.
        """
        scope = await check(bank_id, write=True)
        if scope not in searches:
            raise ValueError("First run a duplicate search in the original Issue's bank.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,239}", document_id):
            raise ValueError("Invalid document ID.")
        op = str(UUID(operation_id))
        addition = addition.strip()
        if not addition or not source_ref.strip():
            raise ValueError("A sourced, redacted addition is required.")
        args = {"bank_id": bank_id, "document_id": document_id}
        old, failed = await upstream("get_document", args, 30)
        missing = old.get("error") == f"Document '{document_id}' not found"
        if missing and expected_sha256 == "new":
            body, tags, metadata = addition, [], {}
        else:
            if failed or old.get("error") or old.get("bank_id") != bank_id or old.get("id") != document_id:
                raise ValueError("Cannot verify the existing document; reconcile before writing.")
            before = old["original_text"]
            if addition in before:
                return dict(args, status="already_covered", content_sha256=digest(before))
            if digest(before) != expected_sha256:
                raise ValueError("Document already exists or has changed; read and compare before updating.")
            body = before + "\n\n" + addition
            tags, metadata = old.get("tags") or [], dict(old.get("document_metadata") or {})
        metadata.update(project_id=scope.project, last_issue_id=scope.issue,
                        last_source_ref=source_ref, content_sha256=digest(body))
        payload = dict(args, operation_id=op, content=body, tags=tags, metadata=metadata)
        if not missing:
            context = (old.get("retain_params") or {}).get("context")
            if context:
                payload["context"] = context
        return await call("retain", payload)


if __name__ == "__main__":
    from fastmcp import FastMCP
    # Reuse the installed transport, which supports stable async operation IDs.
    transport = runpy.run_path(str(Path.home() / ".kimi-code/hindsight/project_memory.py"))
    app = FastMCP("Knowledge manager project memory")
    bind(app, current_scope, transport["upstream_call"])
    app.run(transport="stdio", show_banner=False)
