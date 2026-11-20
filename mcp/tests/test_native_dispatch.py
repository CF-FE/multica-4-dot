"""Loopback v0.11.0 wire contract for write admission and reconciliation."""

from contextlib import closing
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit
import unittest
from uuid import UUID

from multica_backend.delivery import DeliveryLedger, DispatchCommand, HistoricalIssueUnverified, NewIssue, UnverifiedIssue
from multica_backend.native_dispatch import MulticaDispatch
from multica_backend.native_http import NativeHTTP, NativeHTTPError


WORKSPACE, PROJECT, COORDINATOR, USER, ISSUE, PROPERTY, MAILBOX, WORKFLOW, OTHER, LEGACY = [
    str(UUID(int=n)) for n in range(1, 11)
]
TOKEN = "mul_fixture"
INSTANCE = "fixture"
PRINCIPAL = "dot:fixture"
REQUEST = "dispatch-fixture"
COMMAND = DispatchCommand(INSTANCE, WORKSPACE, PROJECT, COORDINATOR, NewIssue("Verify delivery", "todo"))
MAIL_COMMAND = replace(COMMAND, mailbox_project_id=OTHER, mailbox_job_id="job-1",
                       mailbox_payload_hash="1" * 64, mailbox_recipient="fixture-coordinator")


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, payload=None):
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def authenticate(self, path):
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.reply(401, {"error": TOKEN})
            return False
        expected = None if path in ("/api/me", "/empty", "/redirect", "/cutoff") else WORKSPACE
        if self.headers.get("X-Workspace-ID") != expected:
            self.reply(403, {"error": TOKEN})
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        state = self.server.state
        state.calls.append(("GET", path))
        if not self.authenticate(path):
            return
        if path == "/api/me":
            return self.reply(200, {"id": state.actual_user})
        if path == "/api/projects/" + PROJECT:
            if state.project_hidden:
                return self.reply(404, {"error": "private project " + TOKEN})
            return self.reply(200, state.project)
        if path == "/api/projects/" + PROJECT + "/members":
            return self.reply(200, {"members": state.members, "total": len(state.members)})
        if path == "/api/agents/" + COORDINATOR:
            return self.reply(200, state.agent)
        if path == "/api/issue-statuses":
            return self.reply(200, {"statuses": state.statuses, "total": len(state.statuses)})
        if path == "/api/issue-workflows/" + WORKFLOW:
            return self.reply(200, state.workflow)
        if path.startswith("/api/properties/") and state.empty_property_catalog:
            return self.reply(404, {"error": "property not found"})
        if path == "/api/properties/" + PROPERTY:
            return self.reply(200, state.property)
        if path == "/api/properties/" + MAILBOX:
            return self.reply(200, state.mailbox)
        if path == "/api/properties/" + LEGACY:
            return self.reply(200, state.legacy)
        if path == "/api/issues":
            query = parse_qs(parsed.query)
            field = "metadata" if "metadata" in query else "properties"
            if set(query) != {"project_id", field, "sort", "direction", "limit", "offset"}:
                return self.reply(400, {"error": "unexpected query"})
            requested = json.loads(query[field][0])
            filters = {prop: [value] for prop, value in requested.items()} if field == "metadata" else requested
            limit, offset = int(query["limit"][0]), int(query["offset"][0])
            state.queries.append((filters, limit, offset))
            rows = [
                row for row in state.issues.values()
                if row["project_id"] == query["project_id"][0]
                and all(row[field].get(prop) in values for prop, values in filters.items())
            ] if not state.hide_list_rows else []
            total = len(rows) + int(state.incomplete_lookup)
            return self.reply(200, {"issues": rows[offset:offset + limit], "total": total})
        if path.startswith("/api/issues/"):
            issue = state.issues.get(path.rsplit("/", 1)[-1])
            if not issue:
                return self.reply(404, {"error": "issue missing"})
            if state.corrupt_detail:
                issue = {**issue, "properties": {}}
            if state.hide_metadata_from_detail:
                issue = {**issue, "metadata": {}}
            if state.hide_mailbox_from_detail:
                issue = {**issue, "properties": {key: value for key, value in issue["properties"].items() if key != MAILBOX}}
            return self.reply(200, issue)
        if path == "/empty":
            return self.reply(204)
        if path == "/redirect":
            self.send_response(307)
            self.send_header("Location", "/redirect-destination")
            self.end_headers()
            return
        if path == "/cutoff":
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"{}")
            return
        self.reply(404)

    def do_POST(self):
        path = urlsplit(self.path).path
        state = self.server.state
        state.calls.append(("POST", path))
        if not self.authenticate(path):
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if path == "/api/issues/preview-trigger":
            state.previews.append(body)
            triggers = [{"issue_id": "", "agent_id": COORDINATOR, "source": "assign"}] if state.invocable else []
            return self.reply(200, {"triggers": triggers, "total_count": len(triggers)})
        if path == "/api/issues":
            state.creates.append(body)
            if state.create_started is not None:
                state.create_started.set()
                if not state.release_create.wait(5):
                    return self.reply(500, {"error": "test did not release the send"})
            if state.deny_create:
                return self.reply(403, {"error": TOKEN})
            row = state.add_issue(ISSUE, body["properties"])
            row.update(assignee_id=body["assignee_id"], assignee_type=body["assignee_type"], status=body["status"])
            if state.drop_create_reply:
                with closing(self.connection) as conn:
                    conn.shutdown(socket.SHUT_RDWR)
                return
            return self.reply(201, row)
        self.reply(404)


class Fixture:
    def __init__(self):
        self.actual_user = USER
        self.project_hidden = False
        self.project = {"id": PROJECT, "workspace_id": WORKSPACE, "visibility": "workspace",
                        "workflow_id": WORKFLOW, "archived_at": None}
        self.agent = {"id": COORDINATOR, "workspace_id": WORKSPACE, "archived_at": None, "owner_id": OTHER}
        self.property = {"id": PROPERTY, "workspace_id": WORKSPACE, "type": "text", "archived": False}
        self.mailbox = {**self.property, "id": MAILBOX}
        self.legacy = {**self.property, "id": LEGACY}
        self.workflow = {"id": WORKFLOW, "workspace_id": WORKSPACE, "steps": [{"status_key": "todo"}]}
        self.statuses = [{"key": "todo", "workspace_id": WORKSPACE, "archived_at": None}]
        self.members = [{"project_id": PROJECT, "user_id": USER}]
        self.calls = []
        self.queries = []
        self.previews = []
        self.creates = []
        self.issues = {}
        self.invocable = True
        self.deny_create = False
        self.drop_create_reply = False
        self.hide_list_rows = False
        self.corrupt_detail = False
        self.empty_property_catalog = False
        self.hide_metadata_from_detail = False
        self.hide_mailbox_from_detail = False
        self.incomplete_lookup = False
        self.create_started = None
        self.release_create = None

    def add_issue(self, issue_id, props, **overrides):
        row = {"id": issue_id, "workspace_id": WORKSPACE, "project_id": PROJECT,
               "creator_type": "member", "creator_id": USER, "properties": props, "metadata": {}, **overrides}
        self.issues[issue_id] = row
        return row


class NativeDispatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "requests.sqlite3"
        self.ledger = DeliveryLedger(self.path)
        self.fixture = self.server.state = Fixture()
        self.http = NativeHTTP(origin=self.origin, token=TOKEN)
        self.dispatch = MulticaDispatch(
            self.http, instance_id=INSTANCE, expected_user_id=USER, correlation_property_id=PROPERTY,
            mailbox_property_id=MAILBOX, legacy_mailbox_property_id=LEGACY,
        )

    def deliver(self, command=COMMAND, request_id=REQUEST):
        return self.ledger.deliver(PRINCIPAL, request_id, command, self.dispatch)

    def test_create_persists_correlation_and_reads_issue_independently_of_run(self):
        result = self.deliver()
        self.assertEqual((result.state, result.issue.issue_id), ("confirmed", ISSUE))
        self.assertEqual(self.deliver(), result)
        self.assertEqual(len(self.fixture.creates), 1)
        self.assertEqual(self.fixture.creates[0], {
            "title": COMMAND.new_issue.title, "description": "", "status": "todo",
            "project_id": PROJECT, "assignee_type": "agent", "assignee_id": COORDINATOR,
            "properties": {PROPERTY: result.correlation},
        })
        self.assertEqual(self.fixture.previews, [
            {"is_create": True, "status": "todo", "project_id": PROJECT,
             "assignee_type": "agent", "assignee_id": COORDINATOR}
        ])
        self.assertEqual(self.fixture.calls[-1], ("GET", f"/api/issues/{ISSUE}"))
        self.assertTrue(all("task-runs" not in path for _, path in self.fixture.calls))

    def test_inflight_retry_cannot_repeat_native_post(self):
        self.fixture.create_started = threading.Event()
        self.fixture.release_create = threading.Event()
        with ThreadPoolExecutor() as pool:
            first = pool.submit(self.deliver)
            try:
                self.assertTrue(self.fixture.create_started.wait(3))
                second = self.deliver()
                self.assertEqual(second.state, "unknown")
                self.assertEqual(len(self.fixture.creates), 1)
            finally:
                self.fixture.release_create.set()
            self.assertEqual(first.result(timeout=4).state, "confirmed")

    def test_dropped_create_reply_restarts_with_read_only_reconciliation(self):
        self.fixture.drop_create_reply = True
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "transport_error")
        self.ledger = DeliveryLedger(self.path)
        self.fixture.hide_list_rows = True
        self.assertEqual(self.deliver().state, "unknown")
        self.fixture.hide_list_rows = False
        self.assertEqual(self.deliver().issue.issue_id, ISSUE)
        self.assertEqual(len(self.fixture.creates), 1)

    def test_paginates_exact_property_and_refuses_multiple_matching_rows(self):
        accepted = self.ledger.accept(PRINCIPAL, REQUEST, COMMAND)
        for n in range(26):
            self.fixture.add_issue(str(UUID(int=100 + n)), {PROPERTY: accepted.correlation})
        with self.assertRaises(UnverifiedIssue):
            self.deliver()
        self.assertEqual([offset for _, _, offset in self.fixture.queries], [0, 25])
        self.assertEqual(self.fixture.queries[0][0], {PROPERTY: [accepted.correlation]})
        self.assertFalse(self.fixture.creates)

    def test_missing_page_rows_and_untrusted_detail_do_not_reach_write(self):
        self.fixture.incomplete_lookup = True
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "incomplete_lookup")
        self.fixture.incomplete_lookup = False
        accepted = self.ledger.get(PRINCIPAL, REQUEST)
        self.fixture.add_issue(ISSUE, {PROPERTY: accepted.correlation})
        self.fixture.corrupt_detail = True
        with self.assertRaises(UnverifiedIssue):
            self.deliver()
        self.assertFalse(self.fixture.creates)

    def test_rejects_correlation_written_by_another_native_user(self):
        accepted = self.ledger.accept(PRINCIPAL, REQUEST, COMMAND)
        self.fixture.add_issue(ISSUE, {PROPERTY: accepted.correlation}, creator_id=OTHER)
        with self.assertRaises(NativeHTTPError):
            self.deliver()
        self.assertFalse(self.fixture.creates)

    def test_exact_original_is_reused_and_scope_mismatch_remains_unwritten(self):
        self.dispatch = MulticaDispatch(
            self.http, instance_id=INSTANCE, expected_user_id=USER, correlation_property_id=None,
        )
        original = replace(COMMAND, new_issue=None, original_issue_id=ISSUE)
        self.fixture.add_issue(ISSUE, {}, creator_id=OTHER, project_id=OTHER)
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver(original)
        self.assertEqual(failure.exception.code, "scope_mismatch")
        self.fixture.issues[ISSUE]["project_id"] = PROJECT
        self.assertEqual(self.deliver(original).issue.issue_id, ISSUE)
        self.assertFalse(self.fixture.creates)
        self.assertFalse(self.fixture.queries)

    def test_mailbox_link_is_written_atomically_and_other_request_requires_original(self):
        self.assertEqual(self.deliver(MAIL_COMMAND).issue.issue_id, ISSUE)
        markers = self.fixture.creates[0]["properties"]
        self.assertEqual(set(markers), {PROPERTY, MAILBOX})
        self.assertTrue(markers[MAILBOX].startswith("mcp-mailbox-v1:"))
        with self.assertRaises(HistoricalIssueUnverified) as found:
            self.dispatch.lookup(MAIL_COMMAND, "mcp-dispatch-v1:" + "a" * 64)
        self.assertEqual(found.exception.code, "mailbox_issue_already_exists")
        original = replace(MAIL_COMMAND, new_issue=None, original_issue_id=ISSUE)
        self.assertEqual(self.dispatch.lookup(original, "").issue_id, ISSUE)
        with self.assertRaises(UnverifiedIssue):
            self.dispatch.lookup(replace(original, mailbox_job_id="other-job"), "")
        self.assertEqual(len(self.fixture.creates), 1)

    def test_legacy_raw_job_property_or_metadata_requires_manual_confirmation_before_write(self):
        for properties, metadata in [
            ({LEGACY: MAIL_COMMAND.mailbox_job_id}, {}),
            ({}, {"task_mailbox_job_id": MAIL_COMMAND.mailbox_job_id}),
        ]:
            with self.subTest(properties=properties, metadata=metadata):
                self.fixture.add_issue(ISSUE, properties, metadata=metadata, creator_id=OTHER)
                with self.assertRaises(HistoricalIssueUnverified) as found:
                    self.deliver(MAIL_COMMAND)
                self.assertEqual(found.exception.code, "legacy_mailbox_issue_exists")
                self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "accepted")
                self.assertFalse(self.fixture.creates)
                explicit = replace(MAIL_COMMAND, new_issue=None, original_issue_id=ISSUE)
                self.assertEqual(self.dispatch.lookup(explicit, "").issue_id, ISSUE)

    def test_metadata_only_clou21_shape_blocks_create_and_links_by_exact_original_without_properties(self):
        self.fixture.empty_property_catalog = True
        self.dispatch = MulticaDispatch(
            self.http, instance_id=INSTANCE, expected_user_id=USER, correlation_property_id=None,
        )
        command = replace(MAIL_COMMAND, mailbox_job_id="g8-to-workspace-coordinator-fixture")
        self.fixture.add_issue(
            ISSUE, {}, identifier="CLOU-21", creator_id=OTHER,
            metadata={"task_mailbox_job_id": command.mailbox_job_id, "historical_note": "synthetic fixture"},
        )

        with self.assertRaises(HistoricalIssueUnverified) as found:
            self.deliver(command)
        self.assertEqual(found.exception.code, "legacy_mailbox_issue_exists")
        self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "accepted")
        self.assertEqual(self.fixture.queries[0][0], {"task_mailbox_job_id": [command.mailbox_job_id]})
        self.assertIn(("GET", f"/api/issues/{ISSUE}"), self.fixture.calls)
        self.assertFalse(self.fixture.creates)
        self.assertFalse(self.fixture.previews)
        self.assertFalse(any(path.startswith("/api/properties/") for _, path in self.fixture.calls))

        original = replace(command, new_issue=None, original_issue_id=ISSUE)
        self.assertEqual(self.dispatch.lookup(original, "").issue_id, ISSUE)

    def test_metadata_match_requires_exact_string_same_project_and_detail_readback(self):
        self.dispatch = MulticaDispatch(
            self.http, instance_id=INSTANCE, expected_user_id=USER, correlation_property_id=None,
        )
        job_id = MAIL_COMMAND.mailbox_job_id
        self.fixture.add_issue(ISSUE, {}, project_id=OTHER, creator_id=OTHER, metadata={"task_mailbox_job_id": job_id})
        self.fixture.add_issue(str(UUID(int=70)), {}, metadata={"task_mailbox_job_id": job_id + "-suffix"})
        with self.assertRaises(NativeHTTPError) as missing:
            self.deliver(MAIL_COMMAND)
        self.assertEqual(missing.exception.code, "missing_dispatch_property")
        original = replace(MAIL_COMMAND, new_issue=None, original_issue_id=ISSUE)
        with self.assertRaises(NativeHTTPError) as cross_scope:
            self.dispatch.lookup(original, "")
        self.assertEqual(cross_scope.exception.code, "scope_mismatch")

        self.fixture.issues[ISSUE]["project_id"] = PROJECT
        self.fixture.hide_metadata_from_detail = True
        with self.assertRaises(UnverifiedIssue):
            self.deliver(MAIL_COMMAND)
        with self.assertRaises(UnverifiedIssue):
            self.dispatch.lookup(original, "")
        self.assertFalse(self.fixture.creates)

    def test_incomplete_metadata_search_stops_before_any_write_or_property_check(self):
        self.dispatch = MulticaDispatch(
            self.http, instance_id=INSTANCE, expected_user_id=USER, correlation_property_id=None,
        )
        self.fixture.incomplete_lookup = True
        with self.assertRaises(NativeHTTPError) as lookup:
            self.deliver(MAIL_COMMAND)
        self.assertEqual(lookup.exception.code, "incomplete_lookup")
        self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "accepted")
        self.assertFalse(self.fixture.creates)
        self.assertFalse(self.fixture.previews)

    def test_receipt_requires_request_and_mailbox_markers_from_same_detail(self):
        self.fixture.hide_mailbox_from_detail = True
        with self.assertRaises(UnverifiedIssue):
            self.deliver(MAIL_COMMAND)
        self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "unknown")
        with self.assertRaises(UnverifiedIssue):
            self.deliver(MAIL_COMMAND)
        self.fixture.hide_mailbox_from_detail = False
        self.assertEqual(self.deliver(MAIL_COMMAND).issue.issue_id, ISSUE)
        self.assertEqual(len(self.fixture.creates), 1)

    def test_unverified_identity_and_hidden_project_stop_before_lookup(self):
        self.fixture.actual_user = OTHER
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "identity_mismatch")
        self.assertEqual(self.fixture.calls, [("GET", "/api/me")])
        self.fixture.actual_user = USER
        self.fixture.project_hidden = True
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.http_status, 404)
        self.assertNotIn(TOKEN, str(failure.exception))
        self.assertFalse(self.fixture.queries)
        self.assertFalse(self.fixture.creates)

    def test_named_workflow_status_private_member_and_invoke_are_preflight_checks(self):
        self.fixture.workflow["steps"] = []
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.check, "workflow")
        self.fixture.workflow["steps"] = [{"status_key": "todo"}]
        self.fixture.project["visibility"] = "private"
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "coordinator_owner_not_member")
        self.fixture.members.append({"project_id": PROJECT, "user_id": OTHER})
        self.fixture.invocable = False
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "coordinator_trigger_unverified")
        self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "accepted")
        self.assertFalse(self.fixture.creates)

    def test_archived_property_blocks_new_issue_before_native_post(self):
        self.fixture.property["archived"] = True
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual(failure.exception.code, "archived")
        self.assertEqual(self.ledger.get(PRINCIPAL, REQUEST).state, "accepted")
        self.assertFalse(self.fixture.creates)

    def test_native_denial_is_safe_and_never_reposts_after_claim(self):
        self.fixture.deny_create = True
        with self.assertRaises(NativeHTTPError) as failure:
            self.deliver()
        self.assertEqual((failure.exception.code, failure.exception.http_status), ("forbidden", 403))
        self.assertNotIn(TOKEN, str(failure.exception))
        self.assertEqual(self.deliver().state, "unknown")
        self.assertEqual(len(self.fixture.creates), 1)

    def test_transport_rejects_redirect_absolute_path_and_short_response(self):
        self.assertIsNone(self.http.request("GET", "/empty"))
        for path, code in [
            ("/redirect", "redirect_refused"),
            ("http://example.invalid/path", "invalid_input"),
            ("//example.invalid/path", "invalid_input"),
            ("/cutoff", "incomplete_response"),
        ]:
            with self.subTest(path=path), self.assertRaises(NativeHTTPError) as failure:
                self.http.request("GET", path)
            self.assertEqual(failure.exception.code, code)
        self.assertNotIn(("GET", "/redirect-destination"), self.fixture.calls)
        with self.assertRaises(NativeHTTPError):
            NativeHTTP(origin="http://192.168.1.2", token=TOKEN)
        NativeHTTP(origin="http://192.168.1.2", token=TOKEN, allow_private_http=True)


if __name__ == "__main__":
    unittest.main()
