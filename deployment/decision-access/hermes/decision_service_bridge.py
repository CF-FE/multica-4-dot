"""Expose Hermes' authenticated Decision Service as a workspace-selectable MCP."""

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys

SERVER_NAME = "decision-service"
SERVER_URL = "https://unbalance-presoak-pledge.ngrok-free.dev/decision-service/mcp"
SERVICE_TOOLS = {"evaluate_decision", "get_decision", "record_decision_feedback"}
HERMES_ROOT = Path(os.environ["LOCALAPPDATA"]) / "hermes"
OAUTH_HOME = HERMES_ROOT / "profiles" / "multica-decision-service"
SCHEMA_PATH = Path(__file__).with_name("decision-service-tools.json")

if not (OAUTH_HOME / "mcp-tokens" / f"{SERVER_NAME}.json").is_file():
    raise SystemExit("Hermes Decision Service OAuth credentials are missing.")

# This setting belongs to the MCP child. Multica retains each role's Hermes home.
os.environ["HERMES_HOME"] = str(OAUTH_HOME)
sys.path.insert(0, str(HERMES_ROOT / "hermes-agent"))
import hermes_bootstrap
import httpx2
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from tools.mcp_oauth import suppress_interactive_oauth
from tools.mcp_oauth_manager import get_manager
from tools.mcp_tool import LATEST_HANDSHAKE_VERSION


@asynccontextmanager
async def upstream_session():
    provider = get_manager().get_or_build_provider(
        SERVER_NAME, SERVER_URL, {"redirect_port": 63137}
    )
    if provider is None:
        raise RuntimeError("The Hermes OAuth client could not be initialized.")
    headers = {"mcp-protocol-version": LATEST_HANDSHAKE_VERSION}
    timeout = httpx2.Timeout(15.0, read=120.0)
    async with httpx2.AsyncClient(auth=provider, headers=headers, timeout=timeout) as http:
        async with streamable_http_client(SERVER_URL, http_client=http) as streams:
            upstream_read, upstream_write, *_ = streams
            async with ClientSession(upstream_read, upstream_write) as upstream:
                await upstream.initialize()
                yield upstream


async def refresh_schema():
    async with upstream_session() as upstream:
        result = await upstream.list_tools()
    if {tool.name for tool in result.tools} != SERVICE_TOOLS:
        raise RuntimeError("Decision Service returned an unexpected tool set.")
    temporary = SCHEMA_PATH.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json(by_alias=True, exclude_none=True), encoding="utf-8")
    temporary.replace(SCHEMA_PATH)


async def serve():
    # ACP may discover twice per turn. Serve the last authenticated schema locally
    # so an upstream connection cannot consume the short ACP discovery deadline.
    cached = types.ListToolsResult.model_validate_json(SCHEMA_PATH.read_text(encoding="utf-8"))

    async def list_tools(_context, _params):
        return cached

    async def call_tool(_context, params):
        if params.name not in SERVICE_TOOLS:
            raise ValueError("Unknown Decision Service tool.")
        async with upstream_session() as upstream:
            return await upstream.call_tool(params.name, params.arguments)

    server = Server(SERVER_NAME, on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (down_read, down_write):
        await server.run(down_read, down_write, server.create_initialization_options())


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if arguments not in ([], ["--refresh-schema"]):
        raise SystemExit("Usage: decision_service_bridge.py [--refresh-schema]")
    try:
        with suppress_interactive_oauth():
            asyncio.run(refresh_schema() if arguments else serve())
    except (Exception, KeyboardInterrupt) as exc:
        raise SystemExit(f"Decision Service MCP connection ended ({type(exc).__name__}).") from None
