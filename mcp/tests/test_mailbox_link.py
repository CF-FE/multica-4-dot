import hashlib
import json
import os
import unittest
from copy import deepcopy
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from multica_backend.mailbox import Mailbox, MailboxError


WORKSPACE = "b66a1205-479f-4c95-b938-b6e3ed436108"
PROJECT = "d785bd5e-0d53-44e4-948d-4a93d429e460"
OTHER_PROJECT = "84d434a8-9285-4a08-8c97-110ad222bb95"
RECIPIENT = "multica-workspace-coordinator"
JOB = "example-existing-job"
ROUTE = "task-mailbox:original-job"
SUBJECT = "github:mailbox-fixture"
TOKEN = "independent-synthetic-mailbox-token"
TIME = "2026-11-20T06:41:11.693+00:00"


def digest(value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(body).hexdigest()


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        if status == 302:
            self.send_header("Location", "/untrusted")
        self.end_headers()
        if body is not None:
            self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        fixture = self.server.fixture
        assert self.path == "/mailbox/mcp"
        assert self.headers.get("Authorization") == f"Bearer {TOKEN}"
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        method = request["method"]
        if fixture.http_status:
            self.respond(fixture.http_status)
            return
        if method == "initialize":
            fixture.handshakes += 1
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}
        else:
            assert self.headers.get("MCP-Protocol-Version") == "2025-11-25"
            if method == "notifications/initialized":
                self.respond(202)
                return
            assert method == "tools/call"
            name = request["params"]["name"]
            args = request["params"]["arguments"]
            fixture.calls.append((name, args))
            if name == "whoami":
                data = fixture.identity
            elif name == "get_job":
                assert args == {"job_id": JOB}
                data = fixture.job
            elif name == "get_result":
                assert args == {"job_id": JOB, "version": 1}
                data = fixture.result
            elif name == "list_events":
                assert args["recipient"] == RECIPIENT
                data = fixture.pages[args["cursor"]]
            else:
                raise AssertionError(f"unexpected tool {name}")
            if fixture.error_tool == name:
                result = {
                    "isError": True,
                    "content": [{"type": "text", "text": fixture.error_text}],
                }
            elif fixture.text_compat:
                result = {"content": [{"type": "text", "text": json.dumps(data)}]}
            else:
                result = {"structuredContent": data, "content": []}
        self.respond(200, {"jsonrpc": "2.0", "id": request["id"], "result": result})


class MailboxLinkTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.handshakes = 0
        self.http_status = None
        self.error_tool = None
        self.error_text = ""
        self.text_compat = False
        payload = {
            "schema_version": 1,
            "origin_task_id": "source:original-task",
            "sender": "cloud-dot",
            "recipient": RECIPIENT,
            "report_route": ROUTE,
            "target": {"workspace_id": WORKSPACE, "project_id": PROJECT},
            "content": "任务原文留在信箱",
        }
        self.job = {"job_id": JOB, "payload": payload, "payload_hash": digest(payload),
                    "status": "PERSISTED", "cancel_requested": False, "latest_result_version": 0}
        body = {"summary": "已核对", "evidence": ["run:sample"]}
        self.result = {"job_id": JOB, "version": 1, "result": body, "result_hash": digest(body),
                       "status": "REPORTED_COMPLETED", "event_id": "result-v1", "created_at": TIME}
        self.identity = {"service": "task-mailbox", "execution_enabled": False, "subject": SUBJECT}
        self.pages = {0: {"events": [], "next_cursor": 0, "has_more": False}}
        server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        server.fixture = self
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.env = {
            "MULTICA_BACKEND_MAILBOX_URL": f"https://127.0.0.1:{server.server_port}/mailbox/mcp",
            "MULTICA_BACKEND_MAILBOX_ACCESS_TOKEN": TOKEN,
            "MULTICA_BACKEND_MAILBOX_SUBJECT": SUBJECT,
        }
        transport = patch("multica_backend.mailbox.HTTPSConnection", HTTPConnection)
        transport.start()
        self.addCleanup(transport.stop)

    def client(self, **overrides):
        with patch.dict(os.environ, self.env | overrides, clear=True):
            return Mailbox.from_env()

    def verify(self, client=None, **updates):
        args = {"job_id": JOB, "payload_hash": self.job["payload_hash"], "workspace_id": WORKSPACE,
                "project_id": PROJECT, "recipient": RECIPIENT, "instance_id": "fixture", "coordinator_id": PROJECT}
        return (client or self.client()).verify_job(**(args | updates))

    def ack(self, cursor, *, job_id=JOB, version=1, result_hash=None):
        return {"event_type": "RESULT_READ_ACKNOWLEDGED", "job_id": job_id,
                "event_id": f"read-{cursor}", "cursor": cursor, "created_at": TIME,
                "data": {"version": version, "result_hash": result_hash or self.result["result_hash"]}}

    def test_lazy_independent_connection_and_minimal_dispatch_reference(self):
        client = self.client()
        self.assertEqual(self.handshakes, 0)
        record = self.verify(client)
        self.assertEqual(record, {
            "job_id": JOB, "payload_hash": self.job["payload_hash"], "report_route": ROUTE,
            "status": "PERSISTED", "latest_result_version": 0,
        })
        self.assertEqual(self.calls, [("whoami", {}), ("get_job", {"job_id": JOB})])

    def test_configuration_and_input_fail_before_network(self):
        with patch.dict(os.environ, {}, clear=True):
            unconfigured = Mailbox.from_env()
        with self.assertRaisesRegex(MailboxError, "not_configured"):
            self.verify(unconfigured)
        with self.assertRaisesRegex(MailboxError, "invalid_endpoint"):
            self.verify(self.client(MULTICA_BACKEND_MAILBOX_URL="http://127.0.0.1/mailbox/mcp"))
        with self.assertRaisesRegex(MailboxError, "invalid_input"):
            self.client().receipt(job_id=JOB, version=True)
        self.assertEqual(self.handshakes, 0)

    def test_digest_target_recipient_route_and_cancellation_fail_closed(self):
        with self.assertRaisesRegex(MailboxError, "payload_hash_mismatch"):
            self.verify(payload_hash="0" * 64)
        with self.assertRaisesRegex(MailboxError, "target_mismatch"):
            self.verify(project_id=OTHER_PROJECT)
        with self.assertRaisesRegex(MailboxError, "recipient_mismatch"):
            self.verify(recipient="cloud-dot")
        original_payload = deepcopy(self.job["payload"])
        self.job["payload"]["report_route"] = "https://sink.invalid/mcp"
        with self.assertRaisesRegex(MailboxError, "payload_hash_mismatch"):
            self.verify()
        self.job["payload_hash"] = digest(self.job["payload"])
        with self.assertRaisesRegex(MailboxError, "route_mismatch"):
            self.verify()
        self.job["payload"], self.job["payload_hash"] = original_payload, digest(original_payload)
        self.job["cancel_requested"] = True
        with self.assertRaisesRegex(MailboxError, "cancel_requested"):
            self.verify()

    def test_precise_ack_pagination_uses_original_jobs_recipient(self):
        self.text_compat = True
        self.pages = {
            0: {"events": [self.ack(4, job_id="unrelated-job"), self.ack(6, version=2)],
                "next_cursor": 6, "has_more": True},
            6: {"events": [self.ack(8, result_hash="a" * 64), self.ack(9)],
                "next_cursor": 9, "has_more": False},
        }
        record = self.client().receipt(job_id=JOB, version=1)
        self.assertEqual(record, self.result | {
            "read_ack_status": "recorded",
            "read_ack": {"event_id": "read-9", "cursor": 9, "created_at": TIME,
                         "version": 1, "result_hash": self.result["result_hash"]},
        })
        self.assertEqual([name for name, _ in self.calls], ["whoami", "get_job", "get_result",
                                                           "list_events", "list_events"])

    def test_recent_result_does_not_imply_ack_or_prevent_exact_older_read(self):
        self.job.update(status="REPORTED_COMPLETED", latest_result_version=2, cancel_requested=True)
        record = self.client().receipt(job_id=JOB, version=1)
        self.assertEqual((record["version"], record["read_ack_status"], record["read_ack"]),
                         (1, "not_observed", None))
        self.result["result"]["summary"] = "changed"
        with self.assertRaisesRegex(MailboxError, "result_hash_mismatch"):
            self.client().receipt(job_id=JOB, version=1)

    def test_scan_limit_surfaces_unknown_without_manufacturing_an_ack(self):
        self.pages = {0: {"events": [self.ack(2, version=2)], "next_cursor": 2, "has_more": True}}
        with patch("multica_backend.mailbox._ACK_PAGE_LIMIT", 1):
            record = self.client().receipt(job_id=JOB, version=1)
        self.assertEqual((record["read_ack_status"], record["read_ack"]), ("unknown", None))

    def test_identity_permission_and_network_errors_are_distinct_and_sanitized(self):
        unauthorized = self.client(MULTICA_BACKEND_MAILBOX_SUBJECT="github:wrong")
        with self.assertRaisesRegex(MailboxError, "identity_mismatch"):
            self.verify(unauthorized)
        self.assertEqual(self.calls, [("whoami", {})])
        self.http_status = 401
        with self.assertRaisesRegex(MailboxError, "unauthenticated"):
            self.verify()
        self.http_status = 302
        with self.assertRaisesRegex(MailboxError, "redirect_refused"):
            self.verify()
        self.http_status = None
        self.error_tool, self.error_text = "get_job", f"AUTHORIZATION_DENIED: {TOKEN}"
        with self.assertRaisesRegex(MailboxError, "forbidden") as error:
            self.verify()
        self.assertNotIn(TOKEN, str(error.exception))
        with patch("multica_backend.mailbox.HTTPSConnection", side_effect=OSError(TOKEN)):
            with self.assertRaisesRegex(MailboxError, "unavailable") as error:
                self.verify()
        self.assertNotIn(TOKEN, str(error.exception))
