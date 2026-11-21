import importlib.util
import json
from pathlib import Path
import unittest

from fastmcp import Client, FastMCP
from fastmcp.server import create_proxy


spec = importlib.util.spec_from_file_location("adapter", Path(__file__).with_name("decision_agent_stdio.py"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class FeedbackRevisionTest(unittest.IsolatedAsyncioTestCase):
    def test_revision_range(self):
        for value in [1, 2**53 + 1, adapter.MAX_REVISION]:
            self.assertEqual(adapter.feedback_event(json.dumps({"revision": value}))["revision"], value)
        for value in [False, 1.5, -1, 0, "1", adapter.MAX_REVISION + 1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapter.feedback_event(json.dumps({"revision": value}))

    async def test_tool_projection_and_forwarding(self):
        upstream = FastMCP("fixture")
        received = []

        @upstream.tool
        def record_decision_feedback(revision: int, event_id: str, payload: dict,
                                     supersedes_revision: int | None = None) -> str:
            received.append((revision, event_id, supersedes_revision, payload))
            return "stored"

        @upstream.tool
        def get_decision(request_id: str) -> str:
            return request_id

        proxy = create_proxy(Client(upstream), name="fixture proxy")
        proxy.add_middleware(adapter.FeedbackEventJSON())
        async with Client(proxy) as client:
            tools = {t.name: t for t in await client.list_tools()}
            props = tools[adapter.FEEDBACK].input_schema["properties"]
            self.assertEqual(props["event_json"]["type"], "string")
            self.assertEqual(tools["get_decision"].input_schema["properties"]["request_id"]["type"], "string")
            payload = {"evidence_refs": ["issue-1", "run-2"], "reason_codes": [], "status": "applied"}
            first = {"revision": 1, "event_id": "same", "payload": payload}
            second = {**first, "revision": 2, "supersedes_revision": 1}
            for event in (first, second):
                await client.call_tool(adapter.FEEDBACK, {"event_json": json.dumps(event)})
            self.assertEqual(received, [(1, "same", None, payload), (2, "same", 1, payload)])


if __name__ == "__main__":
    unittest.main()
