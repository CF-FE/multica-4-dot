"""Exercise the assembled MCP against a loopback native API and a synthetic original-job reader."""

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from multica_backend.gateway import Gateway, Instance, TOOL_CATALOG, Workspace
from multica_backend.mailbox import MailboxError
from multica_backend.server import build_app
from test_gateway_http import LoopbackOAuth, request, serve_loopback
from test_native_dispatch import COORDINATOR, INSTANCE, MAILBOX, PROJECT, PROPERTY, TOKEN, USER, WORKSPACE, Fixture, FixtureHandler


PRINCIPAL = "github:1002"
REQ = str(UUID(int=800))
JOB = {"job_id": "dot-job-8", "payload_hash": "a" * 64}
SCOPE = {"instance_id": INSTANCE, "workspace_id": WORKSPACE, "project_id": PROJECT}
NEW = {**SCOPE, "request_id": REQ, "new_issue": {"title": "Read the original", "status": "todo"}, "mailbox": JOB}


class MailboxReader:
    def __init__(self):
        self.cancelled = False
        self.version = 0
        self.verified = []

    def verify_job(self, **args):
        self.verified.append(args)
        if self.cancelled:
            raise MailboxError("cancel_requested")
        return {"latest_result_version": self.version}

    def receipt(self, *, job_id, version):
        return {"job_id": job_id, "version": version, "read_ack_status": "not_observed"}


class IntegratedGatewayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        scope = Workspace(COORDINATOR, PROPERTY, "workspace-coordinator", MAILBOX)
        self.inst = Instance(f"http://127.0.0.1:{self.server.server_port}", USER, TOKEN, False,
                             frozenset([PRINCIPAL]), {WORKSPACE: scope}, frozenset(["dispatch_issue", "create_project"]))
        self.gw = Gateway({INSTANCE: self.inst}, self.path)
        self.native = self.server.state = Fixture()
        self.mailbox = MailboxReader()
        patcher = patch.object(Gateway, "_mailbox", return_value=self.mailbox)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_streamable_http_dispatch_receipt_and_duplicate(self):
        app = build_app(self.gw, TOOL_CATALOG, LoopbackOAuth())
        with serve_loopback(app) as client:
            def call(name, args):
                response = request(client, "tools/call", {"name": name, "arguments": args}, bearer="fixture-write")
                self.assertEqual(response.status_code, 200)
                return response.json()["result"]["structuredContent"]

            self.assertEqual(call("get_project", SCOPE)["workspace_id"], WORKSPACE)
            receipt = call("dispatch_issue", NEW)
            self.assertEqual(receipt["state"], "confirmed", receipt)
            self.assertEqual(receipt, call("dispatch_issue", NEW))
            self.assertEqual(receipt, call("get_dispatch", {**SCOPE, "request_id": REQ}))
            self.assertEqual(call("get_dispatch_result", {**SCOPE, "request_id": REQ, "version": 1})["job_id"], JOB["job_id"])
            self.assertEqual(len(self.native.creates), 1)
            self.assertIn(JOB["payload_hash"], self.native.creates[0]["description"])
            self.assertEqual(self.mailbox.verified, [{**JOB, "workspace_id": WORKSPACE, "project_id": PROJECT,
                                                     "recipient": "workspace-coordinator"}])

    def test_closed_original_or_duplicate_original_never_launches_again(self):
        self.mailbox.cancelled = True
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["error"]["code"], "cancel_requested")
        self.mailbox.cancelled = False
        self.mailbox.version = 1
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["error"]["code"], "mailbox_job_already_reported")
        self.assertEqual(len(self.native.creates), 0)
        self.mailbox.version = 0
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        duplicate = self.gw.call(PRINCIPAL, "dispatch_issue", {**NEW, "request_id": str(UUID(int=801))})
        self.assertEqual(duplicate["error"]["code"], "request_conflict")
        self.assertEqual(len(self.native.creates), 1)

    def test_restart_after_response_loss_and_revoked_scope(self):
        self.native.drop_create_reply = True
        failed = self.gw.call(PRINCIPAL, "dispatch_issue", NEW)
        self.assertIn("error", failed)
        self.assertEqual(len(self.native.creates), 1)
        restarted = Gateway({INSTANCE: self.inst}, self.path)
        self.assertEqual(restarted.recover(set())["checked"], 0)
        self.assertEqual(restarted.recover({PRINCIPAL})["confirmed"], 1)
        self.assertEqual(len(self.native.creates), 1)
        revoked = Gateway({INSTANCE: replace(self.inst, principals=frozenset())}, self.path)
        self.assertEqual(revoked.call(PRINCIPAL, "get_dispatch", {**SCOPE, "request_id": REQ})["error"]["code"],
                         "scope_unavailable")

    def test_write_keys_are_shared_across_tools_and_arguments_cannot_set_origin(self):
        self.assertIn("error", self.gw.call(PRINCIPAL, "get_project", {**SCOPE, "origin": "https://example.invalid"}))
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        collision = self.gw.call(PRINCIPAL, "create_project", {"instance_id": INSTANCE, "workspace_id": WORKSPACE,
                                                               "title": "Another action", "request_id": REQ})
        self.assertEqual(collision["error"]["code"], "request_conflict")
        self.assertNotIn(TOKEN, json.dumps(collision))
