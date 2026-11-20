"""Loopback HTTP and SQLite integration for v0.11.0 native gateway operations."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from urllib.parse import urlencode
from uuid import UUID

from multica_backend.native_http import NativeHTTP, NativeHTTPError
from multica_backend.native_operations import NativeOperationError, NativeOperations, OPERATION_TOOLS


USER, WS, PROJECT, ISSUE, RUN, AGENT, REVIEWER, NEW_PROJECT, NEW_RUN, COMMENT, REQUEST, OTHER = (
    str(UUID(int=i)) for i in range(1, 13)
)
AUTH = "mul_fixture_bearer"
HIDDEN = "synthetic_raw_response"
WORKSPACE_PATH = f"/api/workspaces/{WS}"
PROJECT_PATH = f"/api/projects/{PROJECT}"
ISSUE_PATH = f"/api/issues/{ISSUE}"
HISTORY_PATH = ISSUE_PATH + "/task-runs?scope=issue&view=timeline"
NOTE_PATH = ISSUE_PATH + "/comments"
SUPPLEMENT_PATH = f"{ISSUE_PATH}/tasks/{RUN}/supplements"
CANCEL_PATH = f"{ISSUE_PATH}/tasks/{RUN}/cancel"
RERUN_PATH = f"/api/tasks/{RUN}/rerun"
PREVIEW_PATH = ISSUE_PATH + "/workflow-handoff?status=in_review"
STATUS_PATH = "/api/issue-statuses"


def issues_path(*, limit=50, offset=0, status=None):
    query = {"project_id": PROJECT, "limit": limit, "offset": offset, "sort": "created_at", "direction": "desc"}
    if status is not None:
        query["status"] = status
    return "/api/issues?" + urlencode(query)


def project_row(project_id=PROJECT, **fields):
    return {"id": project_id, "workspace_id": WS, "title": "Example", "status": "planned",
            "visibility": "workspace", "lead_id": None, "lead_type": None, "description": HIDDEN, **fields}


def issue_row(**fields):
    return {"id": ISSUE, "workspace_id": WS, "project_id": PROJECT, "status": "in_progress",
            "revision": 5, "assignee_type": "agent", "assignee_id": AGENT, **fields}


def run_row(run_id=RUN, **fields):
    return {"id": run_id, "workspace_id": WS, "issue_id": ISSUE, "agent_id": AGENT,
            "status": "running", "can_supplement": True, "result": HIDDEN, **fields}


def comment_row(body, **fields):
    return {"id": COMMENT, "issue_id": ISSUE, "author_id": USER, "author_type": "member",
            "type": "comment", "parent_id": None, "content": body["content"], **fields}


def fixture_routes():
    return {
        ("GET", "/api/me"): {"id": USER, "email": HIDDEN},
        ("GET", WORKSPACE_PATH): {"id": WS, "name": "Fixture", "slug": "fixture", "context": HIDDEN},
        ("GET", PROJECT_PATH): project_row(),
        ("GET", ISSUE_PATH): issue_row(),
        ("GET", HISTORY_PATH): [run_row()],
        ("GET", WORKSPACE_PATH + "/members"): [{"workspace_id": WS, "user_id": REVIEWER, "email": HIDDEN}],
        **{("GET", f"/api/agents/{agent}"): {"id": agent, "workspace_id": WS, "name": "Fixture Agent",
                                             "status": "idle", "archived_at": None, "runtime_id": OTHER,
                                             "system_key": "mika", "mcp_config": HIDDEN}
           for agent in (AGENT, REVIEWER)},
    }


@contextmanager
def fixture(overrides=()):
    routes = {**fixture_routes(), **dict(overrides)}
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def serve_json(self):
            body = None
            if count := int(self.headers.get("Content-Length", "0")):
                body = json.loads(self.rfile.read(count))
            method, path = self.command, self.path
            token, workspace = self.headers.get("Authorization"), self.headers.get("X-Workspace-ID")
            calls.append((method, path, workspace, body))
            if token != "Bearer " + AUTH:
                status, reply = 401, {"error": HIDDEN}
            elif not (path == "/api/me" or path.startswith("/api/workspaces/") or workspace == WS):
                status, reply = 403, {"error": HIDDEN}
            else:
                reply = routes.get((method, path), (404, {"error": HIDDEN}))
                if callable(reply):
                    reply = reply(body)
                if reply is None:
                    return  # Close the socket after the fixture's side effect.
                status, reply = reply if isinstance(reply, tuple) else (200, reply)
            payload = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = do_POST = do_PUT = serve_json

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server, TemporaryDirectory() as tmp:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()

        def adapter(**config):
            return NativeOperations(NativeHTTP(origin=f"http://127.0.0.1:{server.server_port}", token=AUTH), **{
                "instance_id": "fixture", "expected_user_id": USER, "state_path": Path(tmp) / "ledger.sqlite3",
                "coordinator_ids": {WS: AGENT}, **config,
            })

        try:
            yield adapter, calls, routes
        finally:
            server.shutdown()
            thread.join()


def scoped(**fields):
    return {"workspace_id": WS, "project_id": PROJECT, "issue_id": ISSUE, "request_id": REQUEST, **fields}


def writes(calls):
    return [entry for entry in calls if entry[0] != "GET"]


class NativeOperationsTests(unittest.TestCase):
    def test_directory_is_scoped_to_requested_workspace_and_registered_coordinator(self):
        page = {"projects": [project_row()], "total": 3, "has_more": True}
        with fixture({("GET", "/api/projects?limit=1&offset=0"): page}) as (adapter, calls, _):
            api = adapter()
            workspace = api.call("dot", "get_workspace", {"workspace_id": WS})
            projects = api.call("dot", "list_projects", {"workspace_id": WS, "limit": 1})
            coordinator = api.call("dot", "get_coordinator", {"workspace_id": WS})
            self.assertEqual(workspace["workspace_id"], WS)
            self.assertEqual((projects["projects"][0]["project_id"], projects["next_offset"]), (PROJECT, 1))
            self.assertEqual(coordinator["agent_id"], AGENT)
            self.assertNotIn(HIDDEN, repr((workspace, projects, coordinator)))
            with self.assertRaisesRegex(NativeOperationError, "coordinator_not_registered"):
                adapter(coordinator_ids={}).call("dot", "get_coordinator", {"workspace_id": WS})
            self.assertFalse(writes(calls))

    def test_catalog_requires_workspace_for_every_action_and_stable_id_for_every_write(self):
        for tool in OPERATION_TOOLS:
            fields = tool["inputSchema"]["required"]
            self.assertIn("workspace_id", fields)
            self.assertEqual("request_id" in fields, not tool["readOnly"])

    def test_lists_a_verified_project_page_and_projects_only_issue_summary_fields(self):
        row = issue_row(identifier="FX-14", title="Original task", status="qa_waiting", priority="high",
                        due_date=None, description=HIDDEN, attachments=[HIDDEN], comments=[HIDDEN], metadata={"raw": HIDDEN})
        catalog = {"statuses": [{"workspace_id": WS, "key": "qa_waiting", "archived_at": None}], "total": 1}
        path = issues_path(limit=1, offset=2, status="qa_waiting")
        with fixture({("GET", STATUS_PATH): catalog, ("GET", path): {"issues": [row], "total": 4}}) as (adapter, calls, _):
            result = adapter().call("dot", "list_issues", {
                "workspace_id": WS, "project_id": PROJECT, "limit": 1, "offset": 2, "status": "qa_waiting",
            })
            self.assertEqual(result, {"instance_id": "fixture", "workspace_id": WS, "project_id": PROJECT,
                                      "total": 4, "next_offset": 3, "issues": [{
                                          "issue_id": ISSUE, "identifier": "FX-14", "title": "Original task",
                                          "status": "qa_waiting", "priority": "high", "assignee_type": "agent",
                                          "assignee_id": AGENT, "due_date": None, "revision": 5,
                                      }]})
            self.assertEqual([call[1] for call in calls], ["/api/me", PROJECT_PATH, STATUS_PATH, path])

    def test_empty_and_historical_unfiltered_issue_pages_are_read_without_status_catalog(self):
        row = issue_row(identifier="FX-11", title="Original task", status="historical_key", priority="none",
                        due_date="2026-11-20", assignee_id=None, assignee_type=None)
        with fixture({("GET", issues_path()): {"issues": [row], "total": 1},
                      ("GET", issues_path(offset=1)): {"issues": [], "total": 1}}) as (adapter, calls, _):
            args = {"workspace_id": WS, "project_id": PROJECT}
            result = adapter().call("dot", "list_issues", args)
            self.assertEqual(result["issues"][0]["status"], "historical_key")
            self.assertIsNone(result["next_offset"])
            self.assertEqual(adapter().call("dot", "list_issues", {**args, "offset": 1})["issues"], [])
            self.assertNotIn(STATUS_PATH, [call[1] for call in calls])

    def test_issue_list_refuses_wrong_scope_ignored_status_and_invalid_pages(self):
        catalog = {"statuses": [{"workspace_id": WS, "key": "done", "archived_at": None}], "total": 1}
        row = issue_row(identifier="FX-10", title="Issue", status="done", priority="none", due_date=None)
        cases = [
            ([{**row, "project_id": OTHER}], 1, "scope_mismatch"),
            ([{**row, "workspace_id": OTHER}], 1, "scope_mismatch"),
            ([{**row, "status": "in_progress"}], 1, "issue_status_filter_mismatch"),
            ([row, row], 2, "native_schema_drift"),
            ([], 1, "native_schema_drift"),
        ]
        for items, total, code in cases:
            with self.subTest(code=code, total=total), fixture({
                ("GET", STATUS_PATH): catalog, ("GET", issues_path(status="done")): {"issues": items, "total": total},
            }) as (adapter, calls, _):
                with self.assertRaisesRegex(NativeOperationError, code):
                    adapter().call("dot", "list_issues", {"workspace_id": WS, "project_id": PROJECT, "status": "done"})
                self.assertFalse(writes(calls))

    def test_issue_list_checks_project_visibility_and_rejects_an_unknown_or_cross_scope_status(self):
        args = {"workspace_id": WS, "project_id": PROJECT, "status": "done"}
        with fixture({("GET", PROJECT_PATH): (404, {"error": HIDDEN})}) as (adapter, calls, _):
            with self.assertRaises(NativeHTTPError):
                adapter().call("dot", "list_issues", args)
            self.assertEqual([call[1] for call in calls], ["/api/me", PROJECT_PATH])
        for row, code in [({"workspace_id": WS, "key": "todo"}, "unknown_issue_status"),
                          ({"workspace_id": OTHER, "key": "done"}, "scope_mismatch")]:
            with self.subTest(code=code), fixture({("GET", STATUS_PATH): {"statuses": [row], "total": 1}}) as (adapter, calls, _):
                with self.assertRaisesRegex(NativeOperationError, code):
                    adapter().call("dot", "list_issues", args)
                self.assertEqual([call[1] for call in calls], ["/api/me", PROJECT_PATH, STATUS_PATH])

    def test_create_project_validates_workspace_visible_receipt_and_survives_restart(self):
        def create(body):
            return 201, project_row(NEW_PROJECT, **body)

        with fixture({("POST", "/api/projects"): create,
                      ("GET", f"/api/projects/{NEW_PROJECT}"): project_row(NEW_PROJECT)}) as (adapter, calls, _):
            args = {"workspace_id": WS, "request_id": REQUEST, "title": " New ", "priority": "high",
                    "lead_type": "member", "lead_id": REVIEWER, "due_date": "2026-11-21"}
            receipt = adapter().call("dot", "create_project", args)
            self.assertEqual(receipt["receipt"]["project_id"], NEW_PROJECT)
            self.assertEqual(receipt, adapter().call("dot", "create_project", {**args, "title": "New"}))
            with self.assertRaisesRegex(NativeOperationError, "request_conflict"):
                adapter().call("dot", "create_project", {**args, "title": "Another"})
            self.assertEqual(writes(calls), [("POST", "/api/projects", WS, {
                "title": "New", "priority": "high", "lead_type": "member", "lead_id": REVIEWER,
                "due_date": "2026-11-21", "visibility": "workspace",
            })])

    def test_project_update_can_clear_due_date_but_private_lead_changes_are_rejected(self):
        with fixture({("PUT", PROJECT_PATH): lambda body: project_row(**body)}) as (adapter, calls, routes):
            args = {"workspace_id": WS, "project_id": PROJECT, "request_id": REQUEST,
                    "priority": "high", "due_date": None}
            result = adapter().call("dot", "update_project", args)
            self.assertEqual(result["receipt"]["observed_fields"], {"priority": "high", "due_date": None})
            routes["GET", PROJECT_PATH] = project_row(visibility="private")
            with self.assertRaisesRegex(NativeOperationError, "project_lead_access_management"):
                adapter().call("dot", "update_project", {**args, "request_id": OTHER,
                                                         "lead_type": "agent", "lead_id": AGENT})
            self.assertEqual(len(writes(calls)), 1)

    def test_issue_update_locks_revision_and_suppresses_assignment_run_by_default(self):
        outcome = {"status": "deferred", "reason_code": "deferred", "target_id": REVIEWER, "target_type": "agent"}
        with fixture({("PUT", ISSUE_PATH): issue_row(revision=6, assignee_id=REVIEWER, priority="high",
                                                       due_date=None, run_outcome=outcome)}) as (adapter, calls, _):
            result = adapter().call("dot", "update_issue", scoped(priority="high", due_date=None,
                                    assignee_type="agent", assignee_id=REVIEWER, expected_revision=5))
            self.assertEqual(result["status"], "confirmed")
            self.assertEqual(result["receipt"]["run_outcome"], outcome)
            self.assertEqual(writes(calls), [("PUT", ISSUE_PATH, WS, {
                "priority": "high", "due_date": None, "assignee_type": "agent", "assignee_id": REVIEWER,
                "suppress_run": True, "expected_revision": 5,
            })])
            with self.assertRaisesRegex(NativeOperationError, "issue_revision_conflict"):
                adapter().call("dot", "update_issue", scoped(request_id=OTHER, priority="high", expected_revision=4))
            self.assertEqual(len(writes(calls)), 1)

    def test_issue_assignment_can_explicitly_trigger_native_dispatch(self):
        outcome = {"status": "queued", "reason_code": "enqueued", "target_id": REVIEWER, "target_type": "agent"}
        with fixture({("PUT", ISSUE_PATH): issue_row(revision=6, assignee_id=REVIEWER, run_outcome=outcome)}) as (adapter, calls, _):
            args = scoped(assignee_type="agent", assignee_id=REVIEWER, expected_revision=5, start_run=True)
            gateway = adapter()
            result = gateway.call("dot", "update_issue", args)
            self.assertEqual(result["receipt"]["run_outcome"]["status"], "queued")
            self.assertIs(writes(calls)[0][3]["suppress_run"], False)
            self.assertEqual(gateway.call("dot", "update_issue", args), result)
            self.assertEqual(len(writes(calls)), 1)

    def test_silent_note_is_top_level_and_fails_closed_on_unexpected_trigger(self):
        with fixture({("POST", NOTE_PATH): lambda body: (201, comment_row(body))}) as (adapter, calls, routes):
            result = adapter().call("dot", "add_issue_note", scoped(content="@agent fixture note"))
            self.assertEqual(result["receipt"]["comment_id"], COMMENT)
            self.assertEqual(writes(calls), [("POST", NOTE_PATH, WS,
                                             {"type": "comment", "content": "/note @agent fixture note"})])
            routes["POST", NOTE_PATH] = lambda body: comment_row(body, trigger_outcomes=[{"status": "queued"}])
            result = adapter().call("dot", "add_issue_note", scoped(request_id=OTHER, content="another note"))
            self.assertEqual((result["status"], result["reason"]), ("unknown", "unexpected_note_effect"))
            self.assertNotIn("receipt", result)

    def test_steer_uses_exact_run_supplement_and_returns_pending_receipt(self):
        def supplement(body):
            return 201, comment_row(body, supplements=[{"task_id": RUN, "agent_id": AGENT, "status": "pending"}])

        with fixture({("POST", SUPPLEMENT_PATH): supplement}) as (adapter, calls, routes):
            args = scoped(run_id=RUN, content="Use the original record")
            result = adapter().call("dot", "steer_run", args)
            self.assertEqual(result["receipt"]["supplement_status"], "pending")
            post = writes(calls)[0]
            self.assertEqual(post[:3], ("POST", SUPPLEMENT_PATH, WS))
            self.assertEqual(str(UUID(post[3]["client_request_id"])), post[3]["client_request_id"])
            routes["GET", HISTORY_PATH] = [run_row(status="completed")]
            self.assertEqual(adapter().call("dot", "steer_run", args), result)
            self.assertEqual(len(writes(calls)), 1)

    def test_steer_refuses_fallback_when_the_dedicated_handler_cannot_confirm_a_supplement(self):
        for status in (404, 409, 412):
            with self.subTest(status=status), fixture({("POST", SUPPLEMENT_PATH): (status, {"error": HIDDEN})}) as (adapter, calls, _):
                args = scoped(run_id=RUN, content="This should never become a new Run")
                result = adapter().call("dot", "steer_run", args)
                self.assertEqual((result["status"], result["http_status"]), ("unknown", status))
                self.assertEqual(result, adapter().call("dot", "steer_run", args))
                self.assertEqual([call[1] for call in writes(calls)], [SUPPLEMENT_PATH])

    def test_steer_preflight_and_receipt_require_native_supplement_evidence(self):
        with fixture({("POST", SUPPLEMENT_PATH): lambda body: (201, comment_row(body))}) as (adapter, calls, routes):
            args = scoped(run_id=RUN, content="Only this turn")
            api = adapter()
            routes["GET", HISTORY_PATH] = [run_row(can_supplement=False)]
            with self.assertRaisesRegex(NativeOperationError, "run_supplement_unavailable"):
                api.call("dot", "steer_run", args)
            self.assertFalse(writes(calls))
            routes["GET", HISTORY_PATH] = [run_row()]
            result = api.call("dot", "steer_run", args)
            self.assertEqual((result["status"], result["reason"]), ("unknown", "supplement_receipt_unverified"))
            self.assertEqual([call[1] for call in writes(calls)], [SUPPLEMENT_PATH])

    def test_review_requires_independent_configured_workflow_and_records_handoff(self):
        preview = {"handoff": True, "from_status": "in_progress", "to_status": "in_review",
                   "handler_type": "agent", "handler_id": REVIEWER, "brief": HIDDEN}
        with fixture({("GET", PREVIEW_PATH): preview, ("GET", HISTORY_PATH): [run_row(status="completed")],
                      ("PUT", ISSUE_PATH): issue_row(revision=6, status="in_review", assignee_id=REVIEWER)}) as (adapter, calls, routes):
            result = adapter().call("dot", "request_review", scoped(run_id=RUN))
            self.assertEqual(result["receipt"]["observed_fields"]["assignee_id"], REVIEWER)
            self.assertIsNone(result["receipt"]["run_outcome"])
            self.assertEqual(writes(calls), [("PUT", ISSUE_PATH, WS, {"status": "in_review", "expected_revision": 5})])
            routes["GET", PREVIEW_PATH] = {**preview, "handler_id": AGENT}
            with self.assertRaisesRegex(NativeOperationError, "reviewer_is_source_agent"):
                adapter().call("dot", "request_review", scoped(run_id=RUN, request_id=OTHER))
            self.assertEqual(len(writes(calls)), 1)

    def test_cancel_and_rerun_use_exact_routes_and_validate_native_receipt(self):
        with fixture({("POST", CANCEL_PATH): run_row(status="cancelled", cancelled_by={"type": "member", "id": USER}),
                      ("POST", RERUN_PATH): run_row(NEW_RUN, status="queued", attribution={"rerun_of_task_id": RUN})}) as (adapter, calls, _):
            api = adapter()
            cancelled = api.call("dot", "cancel_run", scoped(run_id=RUN))
            rerun = api.call("dot", "rerun_run", scoped(run_id=RUN, request_id=OTHER, fresh=True))
            self.assertEqual(cancelled["receipt"]["run_status"], "cancelled")
            self.assertEqual((rerun["receipt"]["source_run_id"], rerun["receipt"]["run_id"]), (RUN, NEW_RUN))
            self.assertEqual(writes(calls), [("POST", CANCEL_PATH, WS, {}), ("POST", RERUN_PATH, WS, {"fresh": True})])

    def test_native_authority_is_required_for_cancellation_and_rerun_confirmation(self):
        with fixture({("POST", CANCEL_PATH): run_row(status="cancelled", cancelled_by={"type": "member", "id": OTHER}),
                      ("POST", RERUN_PATH): run_row(NEW_RUN, status="queued", attribution={"rerun_of_task_id": OTHER})}) as (adapter, calls, _):
            api = adapter()
            cancelled = api.call("dot", "cancel_run", scoped(run_id=RUN))
            rerun = api.call("dot", "rerun_run", scoped(run_id=RUN, request_id=OTHER))
            self.assertEqual((cancelled["status"], cancelled["reason"]), ("unknown", "cancellation_receipt_unverified"))
            self.assertEqual((rerun["status"], rerun["reason"]), ("unknown", "rerun_receipt_unverified"))
            self.assertEqual(len(writes(calls)), 2)

    def test_scope_and_identity_errors_abort_before_claim_or_write(self):
        scenarios = [
            ({("GET", "/api/me"): {"id": OTHER}}, "identity_mismatch"),
            ({("GET", PROJECT_PATH): project_row(workspace_id=OTHER)}, "scope_mismatch"),
            ({("GET", ISSUE_PATH): issue_row(project_id=OTHER)}, "scope_mismatch"),
            ({("GET", HISTORY_PATH): [run_row(issue_id=OTHER)]}, "scope_mismatch"),
            ({("GET", HISTORY_PATH): [run_row(project_id=OTHER)]}, "scope_mismatch"),
            ({("GET", HISTORY_PATH): [run_row(restricted=True)]}, "restricted_run"),
            ({("GET", HISTORY_PATH): [run_row(OTHER)]}, "exact_run_not_verified"),
            ({("GET", HISTORY_PATH): [run_row(), run_row()]}, "exact_run_not_verified"),
        ]
        for routes, error in scenarios:
            with self.subTest(error=error), fixture(routes) as (adapter, calls, _):
                with self.assertRaisesRegex(NativeOperationError, error):
                    adapter().call("dot", "cancel_run", scoped(run_id=RUN))
                self.assertFalse(writes(calls))

    def test_lost_response_is_unknown_and_never_resent_after_restart(self):
        with fixture({("POST", NOTE_PATH): lambda _: None}) as (adapter, calls, routes):
            args = scoped(content="may have been stored")
            original = adapter().call("dot", "add_issue_note", args)
            self.assertEqual((original["status"], original["reason"]), ("unknown", "transport_error"))
            self.assertEqual(original, adapter().call("dot", "add_issue_note", args))
            routes["GET", ISSUE_PATH] = (404, {"error": HIDDEN})
            with self.assertRaises(NativeHTTPError):
                adapter().call("dot", "add_issue_note", args)
            self.assertEqual(len(writes(calls)), 1)

    def test_concurrent_duplicates_never_issue_a_second_post(self):
        entered, release = Event(), Event()

        def blocked_note(body):
            entered.set()
            if not release.wait(3):
                return 500, {"error": HIDDEN}
            return 201, comment_row(body)

        with fixture({("POST", NOTE_PATH): blocked_note}) as (adapter, calls, _), ThreadPoolExecutor(2) as pool:
            args = scoped(content="only one")
            first = pool.submit(adapter().call, "dot", "add_issue_note", args)
            try:
                self.assertTrue(entered.wait(3))
                second = pool.submit(adapter().call, "dot", "add_issue_note", args)
                self.assertEqual(second.result(timeout=3)["status"], "unknown")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3)["status"], "confirmed")
            self.assertEqual(len(writes(calls)), 1)


if __name__ == "__main__":
    unittest.main()
