"""Expose the role's Decision Service over stdio with lossless feedback event JSON."""

import json
import os
import sys

from fastmcp import Client
from fastmcp.server import create_proxy
from fastmcp.server.middleware import Middleware


SERVICE_URL = "https://unbalance-presoak-pledge.ngrok-free.dev/decision-service/mcp"
FEEDBACK = "record_decision_feedback"
MAX_REVISION = 2**63 - 1


def feedback_event(text):
    event = json.loads(text)
    if not isinstance(event, dict):
        raise ValueError("Expected a feedback event JSON object")
    for name in ("revision", "supersedes_revision"):
        if name == "supersedes_revision" and event.get(name) is None:
            continue
        value = event.get(name)
        if type(value) is not int or not 1 <= value <= MAX_REVISION:
            raise ValueError(f"Expected a positive 64-bit integer in {name}")
    return event


class FeedbackEventJSON(Middleware):
    async def on_list_tools(self, context, call_next):
        tools = []
        for tool in await call_next(context):
            if tool.name == FEEDBACK:
                parameters = {
                    "type": "object",
                    "properties": {"event_json": {
                        "type": "string",
                        "description": "Complete v1 feedback event as JSON text. Keep revision as a positive integer and evidence_refs, reason_codes and result_refs as JSON arrays where required.",
                    }},
                    "required": ["event_json"],
                    "additionalProperties": False,
                }
                tool = tool.model_copy(update={"parameters": parameters})
            tools.append(tool)
        return tools

    async def on_call_tool(self, context, call_next):
        message = context.message
        if message.name == FEEDBACK:
            args = message.arguments or {}
            if set(args) != {"event_json"} or not isinstance(args["event_json"], str):
                raise ValueError("Supply the complete feedback event as event_json text")
            event = feedback_event(args["event_json"])
            context = context.copy(message=message.model_copy(update={"arguments": event}))
        return await call_next(context)


def main():
    token = os.environ.get("DECISION_AGENT_TOKEN", "")
    if not token.startswith("mds_"):
        raise RuntimeError("Missing dedicated Decision Service credential")
    client = Client(SERVICE_URL, auth=token, mode="legacy", timeout=45, init_timeout=18)
    proxy = create_proxy(client, name="Decision Service")
    proxy.add_middleware(FeedbackEventJSON())
    proxy.run(transport="stdio", show_banner=False, log_level="ERROR")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Decision Service MCP failed ({type(exc).__name__})", file=sys.stderr)
        sys.exit(1)
