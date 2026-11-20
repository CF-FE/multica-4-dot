"""Exercise the assembled MCP against a loopback native API and a synthetic original-job reader."""

from contextlib import closing
import http.client
import json
import socket
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
from urllib.parse import urlsplit

from multica_backend.gateway import Gateway, Instance, TOOL_CATALOG, Workspace
from multica_backend.mailbox import Mailbox, _canonical_digest
from multica_backend.server import build_app
from test_gateway_http import LoopbackOAuth, request, serve_loopback
from test_native_dispatch import (
    COORDINATOR, INSTANCE, ISSUE, MAILBOX, OTHER, PROJECT, PROPERTY, TOKEN, USER, WORKSPACE,
    Fixture, FixtureHandler,
)


PRINCIPAL = "github:1002"
REQ = str(UUID(int=800))
SCOPE = {"instance_id": INSTANCE, "workspace_id": WORKSPACE, "project_id": PROJECT}
PAYLOAD = {"schema_version": 1, "recipient": "workspace-coordinator", "report_route": "task-mailbox:original-job",
           "target": {"workspace_id": WORKSPACE, "project_id": PROJECT}}
JOB = {"job_id": "dot-job-8", "payload_hash": _canonical_digest(PAYLOAD)}
NEW = {**SCOPE, "request_id": REQ, "new_issue": {"title": "Read the original", "status": "todo"}, "mailbox": JOB}
INTAKE = {**SCOPE, "request_id": REQ, "job_id": JOB["job_id"]}
COMMENTS = f"/api/issues/{ISSUE}/comments"
RUN = str(UUID(int=900))
CREATED = "2026-11-20T10:00:00Z"
STARTED = "2026-11-20T10:01:00Z"
AGENT_TOKEN = "fixture-agent-run-token"


class IntakeFixture(Fixture):
    def __init__(self):
        super().__init__()
        self.comments = []
        self.comment_posts = 0
        self.comment_header = None
        self.comments_forbidden = False
        self.drop_note_reply = False
        self.runs = []
        self.assignments = 0

    def add_issue(self, issue_id, props, **overrides):
        row = super().add_issue(issue_id, props, created_at=CREATED, **overrides)
        if props.get(PROPERTY, "").startswith("mcp-dispatch-v1:"):
            self.assignments += 1
            self.runs.append({"id": RUN, "issue_id": issue_id, "agent_id": COORDINATOR,
                              "workspace_id": WORKSPACE, "kind": "direct", "created_at": CREATED,
                              "status": "queued", "started_at": None,
                              "attribution": {"source": "direct_human", "precise": True,
                                              "initiator": {"id": USER},
                                              "evidence": {"kind": "issue_assignment", "ref_id": issue_id}}})
        return row


class IntakeHandler(FixtureHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        state = self.server.state
        if path == COMMENTS:
            if not self.authenticate(path):
                return
            if self.path != path + "?roots_only=true" or state.comments_forbidden:
                return self.reply(403)
            if state.comment_header:
                body = json.dumps(state.comments).encode()
                self.send_response(200)
                self.send_header(state.comment_header, "true")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return self.reply(200, state.comments)
        if path == f"/api/issues/{ISSUE}/task-runs":
            if self.authenticate(path):
                return self.reply(200, state.runs)
            return
        return super().do_GET()

    def do_POST(self):
        state = self.server.state
        if self.path != COMMENTS:
            return super().do_POST()
        if self.headers.get("Authorization") != f"Bearer {AGENT_TOKEN}" or ISSUE not in state.issues:
            return self.reply(403)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("type") != "comment" or not body.get("content", "").startswith("/note "):
            return self.reply(400)
        state.comment_posts += 1
        note = {"id": str(UUID(int=950 + state.comment_posts)), "issue_id": ISSUE, "type": "comment",
                "author_id": COORDINATOR, "author_type": "agent", "parent_id": None,
                "content": body["content"], "created_at": STARTED, "source_task_id": RUN}
        state.comments.append(note)
        if state.drop_note_reply:
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        return self.reply(201, note)


class MailboxReader(Mailbox):
    def __init__(self):
        self.cancelled = False
        self.version = 0
        self.verified = []
        self.payload = PAYLOAD

    def _session(self):
        return self

    def tool(self, name, *, job_id):
        assert name == "get_job" and job_id == JOB["job_id"]
        return {"job_id": job_id, "payload": self.payload, "payload_hash": _canonical_digest(self.payload),
                "cancel_requested": self.cancelled, "status": "PERSISTED" if self.version == 0 else "REPORTED_COMPLETED",
                "latest_result_version": self.version}

    def verify_job(self, **args):
        self.verified.append(args)
        return super().verify_job(**args)

    def receipt(self, *, job_id, version):
        return {"job_id": job_id, "version": version, "read_ack_status": "recorded"}


class IntegratedGatewayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), IntakeHandler)
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
        self.native = self.server.state = IntakeFixture()
        self.mailbox = MailboxReader()
        patcher = patch.object(Gateway, "_mailbox", return_value=self.mailbox)
        patcher.start()
        self.addCleanup(patcher.stop)

    def intake(self, gateway=None, **args):
        return (gateway or self.gw).call(PRINCIPAL, "get_dispatch_acceptance", {**INTAKE, **args})

    def write_note(self, **overrides):
        content = {"event": "mailbox-intake-v1", **JOB, "issue_id": ISSUE,
                   "coordinator_id": COORDINATOR, **overrides}
        body = json.dumps({"type": "comment", "content": "/note " + json.dumps(content)})
        with closing(http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=4)) as client:
            client.request("POST", COMMENTS, body, {"Authorization": f"Bearer {AGENT_TOKEN}"})
            with client.getresponse() as response:
                self.assertEqual(response.status, 201)
                return json.load(response)

    def counts(self):
        return (len(self.native.creates), len(self.native.issues), self.native.assignments,
                len(self.native.runs), self.native.comment_posts, len(self.native.comments))

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
            self.assertEqual(call("get_dispatch_result", {**SCOPE, "request_id": REQ, "version": 1})["read_ack_status"],
                             "recorded")
            pending = call("get_dispatch_acceptance", INTAKE)
            self.assertEqual(pending.get("acceptance", {}).get("state"), "unconfirmed", pending)
            self.assertEqual(pending["run"], {"state": "unconfirmed", "reason": "run_source_unverified",
                                              "candidate": {"id": RUN, "status": "queued"}})
            note = self.write_note()
            self.native.runs[0].update(status="running", started_at=STARTED)
            accepted = call("get_dispatch_acceptance", INTAKE)
            self.assertEqual(accepted["acceptance"], {"state": "accepted", "receipt": {
                "id": note["id"], "author_id": COORDINATOR, "author_type": "agent", "created_at": STARTED,
                "source_task_id": RUN}})
            self.assertEqual(accepted["run"], {"id": RUN, "state": "started", "started_at": STARTED,
                                               "basis": "receipt_source_task"})
            for key, value in {**JOB, "request_id": REQ, "coordinator_id": COORDINATOR}.items():
                self.assertEqual(accepted[key], value)
            self.assertEqual(accepted["issue"], receipt["issue"])
            self.assertEqual(self.counts(), (1, 1, 1, 1, 1, 1))
            self.assertEqual(call("get_dispatch_result", {**SCOPE, "request_id": REQ, "version": 1})["job_id"], JOB["job_id"])
            self.assertEqual(len(self.native.creates), 1)
            self.assertIn(JOB["payload_hash"], self.native.creates[0]["description"])
            self.assertEqual(self.mailbox.verified, [{**JOB, **SCOPE, "coordinator_id": COORDINATOR,
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

    def test_metadata_only_historical_issue_links_without_configured_properties(self):
        scope = Workspace(COORDINATOR, None, "workspace-coordinator")
        instance = replace(self.inst, workspaces={WORKSPACE: scope})
        gateway = Gateway({INSTANCE: instance}, self.path)
        self.native.empty_property_catalog = True
        self.native.add_issue(ISSUE, {}, creator_id=OTHER, metadata={"task_mailbox_job_id": JOB["job_id"]})
        self.mailbox.version = 1
        linked = gateway.call(PRINCIPAL, "dispatch_issue", {
            **SCOPE, "request_id": REQ, "original_issue_id": ISSUE, "mailbox": JOB,
        })
        self.assertEqual((linked.get("state"), linked.get("issue", {}).get("issue_id")), ("confirmed", ISSUE), linked)
        self.assertFalse(self.native.creates)
        self.assertFalse(self.native.previews)

    def test_explicit_original_remains_linked_but_ambiguous_mailbox_binding_stays_unconfirmed(self):
        for issue_id in (ISSUE, OTHER):
            self.native.add_issue(issue_id, {}, creator_id=OTHER, metadata={"task_mailbox_job_id": JOB["job_id"]})
        linked = self.gw.call(PRINCIPAL, "dispatch_issue", {
            **SCOPE, "request_id": REQ, "original_issue_id": ISSUE, "mailbox": JOB,
        })
        self.write_note()
        self.assertEqual(self.gw.call(PRINCIPAL, "get_dispatch", {**SCOPE, "request_id": REQ}), linked)
        ambiguous = self.intake()
        self.assertEqual(ambiguous["issue"]["issue_id"], ISSUE)
        self.assertEqual(ambiguous["acceptance"], {"state": "unconfirmed", "reason": "historical_issue_ambiguous"})
        self.assertEqual(ambiguous["follow_up"]["principal"], PRINCIPAL)
        self.assertEqual(self.counts(), (0, 2, 0, 0, 1, 1))
        del self.native.issues[OTHER]
        self.native.incomplete_lookup = True
        self.assertEqual(self.intake()["acceptance"]["state"], "unconfirmed")
        self.native.incomplete_lookup = False
        self.assertEqual(self.intake()["acceptance"]["state"], "accepted")

    def test_metadata_only_historical_issue_blocks_new_dispatch_before_property_setup(self):
        scope = Workspace(COORDINATOR, None, "workspace-coordinator")
        instance = replace(self.inst, workspaces={WORKSPACE: scope})
        gateway = Gateway({INSTANCE: instance}, self.path)
        self.native.empty_property_catalog = True
        self.native.add_issue(ISSUE, {}, creator_id=OTHER, metadata={"task_mailbox_job_id": JOB["job_id"]})
        found = gateway.call(PRINCIPAL, "dispatch_issue", NEW)
        self.assertEqual(found["error"]["code"], "legacy_mailbox_issue_exists")
        self.assertFalse(self.native.creates)
        self.assertFalse(self.native.previews)

    def test_restart_after_response_loss_and_revoked_scope(self):
        self.native.drop_create_reply = True
        failed = self.gw.call(PRINCIPAL, "dispatch_issue", NEW)
        self.assertIn("error", failed)
        self.assertEqual(len(self.native.creates), 1)
        restarted = Gateway({INSTANCE: self.inst}, self.path)
        self.assertEqual(restarted.recover(set())["checked"], 0)
        self.assertEqual(restarted.recover({PRINCIPAL})["confirmed"], 1)
        self.assertEqual(self.intake(restarted)["run"]["candidate"]["status"], "queued")
        self.native.drop_note_reply = True
        with self.assertRaises(http.client.RemoteDisconnected):
            self.write_note()
        self.native.runs[0].update(status="running", started_at=STARTED)
        restarted = Gateway({INSTANCE: self.inst}, self.path)
        verified = self.intake(restarted)
        self.assertEqual(verified["acceptance"]["receipt"]["id"], self.native.comments[0]["id"])
        self.assertEqual((verified["run"]["state"], verified["run"]["id"]), ("started", RUN))
        self.assertEqual(verified, self.intake(restarted))
        self.assertEqual(restarted.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        self.assertEqual(self.counts(), (1, 1, 1, 1, 1, 1))
        self.assertEqual(len(self.native.creates), 1)
        revoked = Gateway({INSTANCE: replace(self.inst, principals=frozenset())}, self.path)
        self.assertEqual(revoked.call(PRINCIPAL, "get_dispatch", {**SCOPE, "request_id": REQ})["error"]["code"],
                         "scope_unavailable")

    def test_author_digest_scope_and_incomplete_reads_fail_closed(self):
        wrong_digest = self.gw.call(PRINCIPAL, "dispatch_issue", {**NEW, "mailbox": {**JOB, "payload_hash": "b" * 64}})
        self.assertEqual(wrong_digest["error"]["code"], "payload_hash_mismatch")
        for field, value in (("project_id", OTHER), ("instance_id", "other-instance"), ("agent_id", OTHER)):
            with self.subTest(field=field):
                self.mailbox.payload = {**PAYLOAD, "target": {**PAYLOAD["target"], field: value}}
                wrong_target = {**NEW, "mailbox": {**JOB, "payload_hash": _canonical_digest(self.mailbox.payload)}}
                self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", wrong_target)["error"]["code"],
                                 "target_mismatch")
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))
        self.mailbox.payload = PAYLOAD
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        self.write_note(payload_hash="b" * 64)
        self.write_note()
        self.native.comments[-1].update(author_type="member", author_id=USER)
        self.write_note()
        self.native.comments[-1].update(parent_id=self.native.comments[0]["id"])
        self.assertEqual(self.intake()["acceptance"]["state"], "unconfirmed")
        self.assertEqual(self.intake(job_id="other-job")["error"]["code"], "dispatch_unavailable")
        self.assertEqual(self.intake(project_id=OTHER)["error"]["code"], "dispatch_unavailable")
        other_principal = "github:1003"
        instance = replace(self.inst, principals=frozenset([PRINCIPAL, other_principal]))
        self.assertEqual(Gateway({INSTANCE: instance}, self.path).call(other_principal, "get_dispatch_acceptance", INTAKE),
                         {"error": {"code": "dispatch_unavailable"}})
        self.write_note()
        for header in ("X-Comments-Truncated", "X-Multica-Next-Before"):
            self.native.comment_header = header
            self.assertEqual(self.intake()["acceptance"]["state"], "unconfirmed")
        self.native.comment_header = None
        self.native.comments_forbidden = True
        self.assertEqual(self.intake()["acceptance"]["state"], "unconfirmed")
        self.native.comments_forbidden = False
        self.assertEqual(self.intake()["acceptance"]["state"], "accepted")
        self.write_note()
        self.assertEqual(self.intake()["acceptance"]["reason"], "receipt_ambiguous")
        self.assertEqual(self.counts(), (1, 1, 1, 1, 5, 5))

    def test_run_scope_and_later_reruns_cannot_attest_to_startup(self):
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        self.write_note()
        queued = self.native.runs[0]
        queued["started_at"] = STARTED
        rerun = {**queued, "id": str(UUID(int=901)), "status": "running",
                 "attribution": {**queued["attribution"], "rerun_of_task_id": RUN}}
        self.native.runs.append(rerun)
        self.assertEqual(self.intake()["run"], {"id": RUN, "state": "queued"})
        queued["agent_id"] = OTHER
        evidence = self.intake()
        self.assertEqual(evidence["acceptance"]["state"], "accepted")
        self.assertEqual(evidence["run"], {"state": "unconfirmed", "reason": "run_source_unverified",
                                           "candidate": {"id": rerun["id"], "status": "running"}})
        queued.update(agent_id=COORDINATOR, issue_id=OTHER)
        self.assertEqual(self.intake()["run"]["reason"], "scope_mismatch")
        queued["issue_id"] = ISSUE
        queued.update(restricted=True, project_id=None, status="running")
        evidence = self.intake()
        self.assertEqual(evidence["acceptance"]["state"], "accepted")
        self.assertEqual(evidence["run"]["state"], "unconfirmed")
        del queued["project_id"]
        self.assertEqual(self.intake()["run"]["reason"], "restricted_run")
        del queued["restricted"]
        queued.update(status="completed", completed_at=CREATED)
        self.assertEqual(self.intake()["run"]["reason"], "receipt_after_run_completion")
        del self.native.comments[0]["source_task_id"]
        self.assertEqual(self.intake()["run"]["reason"], "run_ambiguous")

    def test_unique_later_assignment_cannot_stand_in_for_the_original_run(self):
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        self.write_note()
        later_id = str(UUID(int=902))
        self.native.runs[0].update(id=later_id, status="running", created_at="2026-11-21T10:00:00Z",
                                  started_at="2026-11-21T10:01:00Z")
        evidence = self.intake()
        self.assertEqual(evidence["acceptance"]["state"], "accepted")
        self.assertEqual(evidence["run"], {"state": "unconfirmed", "reason": "run_source_unverified",
                                           "candidate": {"id": later_id, "status": "running"}})

    def test_occupied_job_stays_read_only_and_reconciles_unique_historical_receipt(self):
        self.native.incomplete_lookup = True
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["error"]["code"], "incomplete_lookup")
        self.assertEqual(self.gw.call(PRINCIPAL, "get_dispatch", {**SCOPE, "request_id": REQ})["state"], "accepted")
        self.native.incomplete_lookup = False
        self.native.add_issue(ISSUE, {}, creator_id=OTHER, metadata={"task_mailbox_job_id": JOB["job_id"]})
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["error"]["code"],
                         "legacy_mailbox_issue_exists")
        clue = self.intake()
        self.assertEqual(clue["candidate_issue_id"], ISSUE)
        self.assertEqual(clue["acceptance"]["state"], "unconfirmed")
        row = self.native.issues.pop(ISSUE)
        restarted = Gateway({INSTANCE: self.inst}, self.path)
        restarted.recover({PRINCIPAL})
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))
        self.assertEqual(self.intake(restarted)["candidate_issue_id"], ISSUE)
        self.native.issues[ISSUE] = row
        self.write_note()
        self.native.add_issue(OTHER, {}, creator_id=OTHER, metadata={"task_mailbox_job_id": JOB["job_id"]})
        restarted.recover({PRINCIPAL})
        self.assertEqual(self.intake(restarted)["acceptance"]["state"], "unconfirmed")
        del self.native.issues[OTHER]
        self.mailbox.version = 1  # A result arriving after registration cannot cause a second dispatch.
        self.assertEqual(restarted.recover({PRINCIPAL})["confirmed"], 1)
        self.native.runs.append({"id": RUN, "issue_id": ISSUE, "agent_id": COORDINATOR,
                                 "workspace_id": WORKSPACE, "status": "completed", "started_at": STARTED})
        reconciled = self.intake(restarted)
        self.assertEqual(reconciled["acceptance"]["state"], "accepted")
        self.assertEqual(reconciled["run"]["state"], "unattributed")
        self.assertEqual(self.counts(), (0, 1, 0, 1, 1, 1))

    def test_write_keys_are_shared_across_tools_and_arguments_cannot_set_origin(self):
        self.assertIn("error", self.gw.call(PRINCIPAL, "get_project", {**SCOPE, "origin": "https://example.invalid"}))
        self.assertEqual(self.gw.call(PRINCIPAL, "dispatch_issue", NEW)["state"], "confirmed")
        collision = self.gw.call(PRINCIPAL, "create_project", {"instance_id": INSTANCE, "workspace_id": WORKSPACE,
                                                               "title": "Another action", "request_id": REQ})
        self.assertEqual(collision["error"]["code"], "request_conflict")
        self.assertNotIn(TOKEN, json.dumps(collision))
