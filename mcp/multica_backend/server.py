"""Streamable HTTP entry point for Multica's authenticated MCP tools."""

import json
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import DEFAULT_MAX_REQUEST_BODY_SIZE, RequestBodyLimitMiddleware
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .auth import AuthError, GitHubOAuth
from .gateway import TOOL_CATALOG, Gateway

logger = logging.getLogger(__name__)


def build_app(gateway, tool_catalog, oauth):
    """Bind the tool gateway and an identity verifier to the MCP transport."""
    tools = {}
    scopes = {}
    for record in tool_catalog:
        name = record["name"]
        read_only = record["readOnly"]
        if name in tools or type(read_only) is not bool:
            raise ValueError("MCP tools require unique names and a boolean readOnly setting")
        tools[name] = Tool(
            name=name,
            description=record["description"],
            inputSchema=record["inputSchema"],
            annotations=ToolAnnotations(readOnlyHint=read_only, openWorldHint=True),
        )
        scopes[name] = "read" if read_only else "write"

    def caller_for(context):
        request = context.request
        return getattr(request.state, "multica_caller", None) if request is not None else None

    def tool_result(result):
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, allow_nan=False))],
            structuredContent=result,
            isError="error" in result,
        )

    async def list_tools(context, _parameters):
        caller = caller_for(context)
        visible = [tool for name, tool in tools.items() if caller and scopes[name] in caller.scopes]
        return ListToolsResult(tools=visible)

    async def call_tool(context, parameters):
        caller = caller_for(context)
        required = scopes.get(parameters.name)
        if caller is None:
            return tool_result({"error": {"code": "unauthenticated"}})
        if required is None:
            return tool_result({"error": {"code": "unknown_tool"}})
        if required not in caller.scopes:
            return tool_result({"error": {"code": "forbidden_scope"}})
        try:
            result = await run_in_threadpool(gateway.call, caller.principal, parameters.name, parameters.arguments or {})
            return tool_result(result)
        except Exception as exc:
            logger.error("MCP tool %s failed (%s)", parameters.name, type(exc).__name__)
            return tool_result({"error": {"code": "internal_error"}})

    server = Server("multica-backend", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool)
    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)

    class Endpoint:
        async def __call__(self, scope, receive, send):
            headers = Headers(scope=scope)
            origins = headers.getlist("origin")
            if origins and origins != [oauth.public_origin]:
                response = JSONResponse({"error": {"code": "forbidden_origin"}}, 403)
                return await response(scope, receive, send)
            authorization = headers.getlist("authorization")
            try:
                caller = await oauth.authenticate(authorization[0] if len(authorization) == 1 else None)
            except AuthError as exc:
                challenge = {"WWW-Authenticate": oauth.challenge} if exc.status == 401 else None
                response = JSONResponse({"error": {"code": exc.code}}, exc.status, headers=challenge)
                return await response(scope, receive, send)
            if scope["method"] != "POST":
                # Stateless JSON exchanges do not expose an independent SSE stream or session deletion.
                return await Response(status_code=405, headers={"Allow": "POST"})(scope, receive, send)
            scope = {**scope, "state": {**scope.get("state", {}), "multica_caller": caller}}
            await manager.handle_request(scope, receive, send)

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    async def health(_request):
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/mcp", Endpoint(), methods=["GET", "POST", "DELETE"]),
            *oauth.routes,
        ],
        lifespan=lifespan,
        middleware=[
            Middleware(
                TrustedHostMiddleware,
                allowed_hosts=[oauth.public_host, "127.0.0.1", "localhost"],
                www_redirect=False,
            ),
            Middleware(RequestBodyLimitMiddleware, max_body_size=DEFAULT_MAX_REQUEST_BODY_SIZE),
        ],
    )


def create_app():
    oauth = GitHubOAuth.from_env()
    return build_app(Gateway.from_env(), TOOL_CATALOG, oauth)


def main():
    port = int(os.getenv("MULTICA_MCP_PORT", "8770"))
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=port,
        workers=1,
        access_log=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
