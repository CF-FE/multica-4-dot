"""Fixture-only verification of the v0.11.0 native REST boundary."""

from contextlib import ExitStack
from copy import deepcopy
import json
import os
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch
from uuid import UUID

from unblock import native


WS, PROJECT, ISSUE, THREAD, COORDINATOR, USER, SUPPLIER, SUMMARY, RUN, RULE, REMINDER_RUN = (
    str(UUID(int=value)) for value in range(1, 12)
)
MARKER = "unblock.v1:" + "a" * 64
ORIGIN = "http://127.0.0.1:8086"
MINUTE_ZERO = "2026-11-21T10:00:00Z"
MINUTE_ONE = "2026-11-21T10:01:00Z"
MINUTE_TWO = "2026-11-21T10:02:00Z"
ISSUE_PATH = f"/api/issues/{ISSUE}"
THREAD_PATH = f"{ISSUE_PATH}/comments?thread={THREAD}"
RUNS_PATH = f"{ISSUE_PATH}/task-runs?scope=issue&view=timeline"
RULES_PATH = f"{ISSUE_PATH}/wakeups"
RULE_RUNS_PATH = f"{RULES_PATH}/{RULE}/runs"
SCOPE = {"instance_id": "fixture", "workspace_id": WS, "project_id": PROJECT, "issue_id": ISSUE,
         "thread_id": THREAD, "coordinator_id": COORDINATOR}
BASE_SNAPSHOT = {**SCOPE, "revision": 1, "checkpoint_id": "review-copy", "mailbox_result_version": 2}


def comment(comment_id, content, *, author=COORDINATOR, author_type="agent",
            at=MINUTE_ONE, parent=THREAD):
    return {"id": comment_id, "content": content, "author_id": author, "author_type": author_type,
            "created_at": at, "updated_at": at, "parent_id": parent, "issue_id": ISSUE,
            "type": "comment"}


class FixtureResponse:
    length = 0

    def __init__(self, data, status=200, headers=None):
        self.status = status
        self.body = json.dumps(data).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self, limit):
        return self.body[:limit]

    def getheader(self, name):
        return self.headers.get(name)


class TestNativeSource(unittest.TestCase):
    def setUp(self):
        self.registration = {
            **SCOPE, "expected_user_id": USER, "cli_path": "/fixture/bin/multica", "cli_profile": "fixture",
            "origin": ORIGIN, "notifications_enabled": True, "checkpoint_id": "review-copy",
            "supplement_authors": [{"type": "member", "id": SUPPLIER}],
        }
        self.config = f"Profile:      fixture\nserver_url:      {ORIGIN}\n"
        self.identity = {"id": USER}
        self.issue = {"id": ISSUE, "workspace_id": WS, "project_id": PROJECT, "status": "in_progress"}
        self.agent = {"id": COORDINATOR, "workspace_id": WS, "name": "Fixture agent",
                      "system_key": "mika", "archived_at": None}
        self.comments = [comment(THREAD, "original thread", parent=None, at=MINUTE_ZERO),
                         comment(SUMMARY, "/note unblock.v1 " + json.dumps(BASE_SNAPSHOT))]
        self.response_headers = {}
        self.runs = []
        self.rules = []
        self.rule_runs = []
        self.statuses = [{"workspace_id": WS, "key": "in_progress", "category": "in_progress"}]
        self.requests = []
        self.posted = []
        self.lose_post = False
        self.read_error = None
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.dict(os.environ, {
            "MULTICA_UNBLOCK_ACCESS_TOKEN": "mul_fixture_only", "MULTICA_TOKEN": "mat_wrong_source",
            "MULTICA_SERVER_URL": "https://wrong.invalid", "HTTPS_PROXY": "https://proxy.invalid",
        }))
        stack.enter_context(patch.object(native.subprocess, "run", side_effect=self.cli))
        stack.enter_context(patch(f"{native.NativeHTTP.__module__}.HTTPConnection", side_effect=self.connection))

    def cli(self, argv, **kwargs):
        self.assertEqual(argv[:3], [self.registration["cli_path"], "--profile", "fixture"])
        self.assertNotIn("MULTICA_TOKEN", kwargs["env"])
        self.assertNotIn("MULTICA_UNBLOCK_ACCESS_TOKEN", kwargs["env"])
        self.assertNotIn("MULTICA_SERVER_URL", kwargs["env"])
        self.assertNotIn("HTTPS_PROXY", kwargs["env"])
        self.assertEqual(argv[3:], ["config", "show"])
        stdout = self.config
        return CompletedProcess(argv, 0, stdout, "")

    def connection(self, host, port, **kwargs):
        self.assertEqual((host, port), ("127.0.0.1", 8086))
        fixture = self

        class Connection:
            def request(self, method, path, *, body, headers):
                self.result = fixture.server(method, path, body, headers)

            def getresponse(self):
                return self.result

            def close(self):
                pass

        return Connection()

    def server(self, method, path, body, headers):
        self.requests.append((method, path))
        self.assertEqual(headers["Authorization"], "Bearer mul_fixture_only")
        self.assertEqual(headers.get("X-Workspace-ID"), None if path == "/api/me" else WS)
        if method == "POST":
            self.assertEqual(path, RULES_PATH)
            body = json.loads(body)
            self.posted.append(body)
            rule = {
                **body, "id": RULE, "workspace_id": WS, "issue_id": ISSUE, "created_by": USER,
                "source_task_id": None, "created_by_agent": False, "revision": 1, "enabled": True,
                "last_task_id": None, "event_types": ["issue.status_changed"], "expiry_seconds": 60,
                "created_at": MINUTE_ONE, "expires_at": MINUTE_TWO,
            }
            self.rules.append(rule)
            if self.lose_post:
                raise OSError("synthetic response loss")
            return FixtureResponse(rule, 201)
        self.assertEqual(method, "GET")
        if self.read_error and self.read_error[0] == path:
            return FixtureResponse({}, self.read_error[1], {"Location": "https://redirect.invalid"})
        fixtures = {
            "/api/me": self.identity, f"/api/projects/{PROJECT}": {"id": PROJECT, "workspace_id": WS},
            ISSUE_PATH: self.issue, f"/api/agents/{COORDINATOR}": self.agent, THREAD_PATH: self.comments,
            RUNS_PATH: self.runs, RULES_PATH: self.rules, RULE_RUNS_PATH: self.rule_runs,
            "/api/issue-statuses": {"statuses": self.statuses},
        }
        return FixtureResponse(fixtures[path], headers=self.response_headers.get(path))

    def new_source(self):
        return native.NativeSource(self.registration)

    def add_supplement(self, number, *, author=SUPPLIER, author_type="member", at=MINUTE_TWO, **scope):
        evidence = {**SCOPE, "checkpoint_id": "review-copy", "evidence_ref": "fixture://evidence", **scope}
        row = comment(str(UUID(int=number)), "/note unblock.evidence.v1 " + json.dumps(evidence),
                      author=author, author_type=author_type, at=at)
        self.comments.append(row)
        return row["id"]

    def begin_reminder_run(self):
        self.rules[0].update(enabled=False, last_task_id=REMINDER_RUN)
        self.rule_runs[:] = [{"id": REMINDER_RUN, "status": "running", "created_at": MINUTE_TWO,
                              "started_at": MINUTE_TWO}]
        self.runs[:] = [{**self.rule_runs[0], "agent_id": COORDINATOR, "workspace_id": WS,
                        "issue_id": ISSUE}]

    def test_poll_rejects_wrong_profile_origin_before_any_network_read(self):
        self.config = self.config.replace(ORIGIN, "https://different.invalid")
        with self.assertRaisesRegex(native.NativeSourceError, "profile_origin_mismatch"):
            self.new_source().poll()
        self.assertEqual(self.requests, [])

    def test_wrong_identity_project_and_coordinator_fail_closed(self):
        for row, change, reason in (
            (self.identity, {"id": SUPPLIER}, "identity_mismatch"),
            (self.issue, {"project_id": SUPPLIER}, "issue_scope_mismatch"),
            (self.agent, {"system_key": "different"}, "coordinator_changed"),
            (self.agent, {"archived_at": MINUTE_TWO}, "coordinator_changed"),
        ):
            with self.subTest(reason=reason), patch.dict(row, change):
                with self.assertRaises(native.NativeSourceError) as captured:
                    self.new_source().poll()
                self.assertEqual(captured.exception.code, reason)

    def test_incomplete_comments_are_rejected_at_http_boundary(self):
        for header in native._INCOMPLETE_COMMENTS:
            with self.subTest(header=header):
                self.response_headers[THREAD_PATH] = {header: "fixture"}
                with self.assertRaisesRegex(native.NativeSourceError, "multica:incomplete_response"):
                    self.new_source().poll()

    def test_redirect_is_not_followed(self):
        self.read_error = THREAD_PATH, 302
        with self.assertRaisesRegex(native.NativeSourceError, "multica:redirect_refused"):
            self.new_source().poll()
        self.assertEqual(self.requests[-1], ("GET", THREAD_PATH))

    def test_wrong_author_is_ignored_and_wrong_thread_fails(self):
        self.comments[1]["author_id"] = SUPPLIER
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_summary_unconfirmed"):
            self.new_source().poll()
        self.comments[1]["parent_id"] = PROJECT
        with self.assertRaisesRegex(native.NativeSourceError, "comment_thread_mismatch"):
            self.new_source().poll()

    def test_conflicting_revision_or_duplicate_json_member_is_rejected(self):
        conflicting = comment(RUN, "/note unblock.v1 " + json.dumps({**BASE_SNAPSHOT, "due_at": MINUTE_TWO}),
                              at=MINUTE_TWO)
        self.comments.append(conflicting)
        with self.assertRaisesRegex(native.NativeSourceError, "ambiguous_summary_revision"):
            self.new_source().poll()
        conflicting["content"] = '/note unblock.v1 {"revision":1,"revision":2}'
        with self.assertRaisesRegex(native.NativeSourceError, "invalid_summary"):
            self.new_source().poll()

    def test_latest_revision_and_authorized_fresh_supplement_only(self):
        snapshot = {**BASE_SNAPSHOT, "revision": 2}
        self.comments.append(comment(RUN, "/note unblock.v1 " + json.dumps(snapshot),
                                     at="2026-11-21T10:01:20Z"))
        self.add_supplement(12, at=MINUTE_ONE)
        self.add_supplement(13, author=COORDINATOR, author_type="agent")
        self.add_supplement(14, author=USER)
        self.add_supplement(15, project_id=SUPPLIER)
        self.add_supplement(16, checkpoint_id="previous-round")
        latest = self.add_supplement(17)
        self.assertEqual(self.new_source().poll(), {
            "snapshot": snapshot, "hints": [f"comment:{latest}"], "pending": [],
            "summary_source": {"comment_id": RUN, "author_id": COORDINATOR, "created_at": "2026-11-21T10:01:20Z"},
        })

    def test_registered_operator_can_post_an_authorized_supplement(self):
        self.registration["supplement_authors"].append({"type": "member", "id": USER})
        supplement = self.add_supplement(17, author=USER)
        self.assertEqual(self.new_source().poll()["hints"], [f"comment:{supplement}"])

    def test_recorded_at_can_precede_but_cannot_follow_native_publication(self):
        row = self.comments[1]
        row["content"] = "/note unblock.v1 " + json.dumps({**BASE_SNAPSHOT, "recorded_at": MINUTE_ZERO})
        observed = self.new_source().poll()
        self.assertEqual(observed["snapshot"]["recorded_at"], MINUTE_ZERO)
        self.assertEqual(observed["summary_source"]["created_at"], MINUTE_ONE)
        row["content"] = "/note unblock.v1 " + json.dumps({**BASE_SNAPSHOT, "recorded_at": MINUTE_TWO})
        with self.assertRaisesRegex(native.NativeSourceError, "summary_recorded_after_publication"):
            self.new_source().poll()

    def test_original_run_only_and_exact_terminal_time(self):
        self.registration["run_id"] = RUN
        row = {"id": RUN, "issue_id": ISSUE, "workspace_id": WS, "agent_id": SUPPLIER,
               "status": "failed", "completed_at": MINUTE_ZERO}
        self.runs = [row, {**row, "id": REMINDER_RUN, "completed_at": MINUTE_TWO}]
        self.assertEqual(self.new_source().poll()["hints"], [])
        row["completed_at"] = MINUTE_TWO
        self.assertEqual(self.new_source().poll()["hints"], [f"run:{RUN}:failed"])
        row["workspace_id"] = PROJECT
        self.assertEqual(self.new_source().poll()["pending"], ["run:run_scope_unconfirmed"])

    def test_equal_native_timestamps_are_kept_as_review_hints(self):
        self.registration["run_id"] = RUN
        self.runs.append({"id": RUN, "issue_id": ISSUE, "workspace_id": WS, "agent_id": SUPPLIER,
                          "status": "completed", "completed_at": MINUTE_ONE})
        supplement = self.add_supplement(17, at=MINUTE_ONE)
        self.assertEqual(self.new_source().poll()["hints"], [
            f"comment:{supplement}", f"run:{RUN}:completed",
        ])

    def test_mailbox_needs_only_read_only_job_verification(self):
        job_ref = {"job_id": "fixture-job", "payload_hash": "7" * 64, "recipient": "coord"}
        self.registration["mailbox"] = job_ref

        class JobReadOnly:
            def verify_job(inner, **arguments):
                self.assertEqual(arguments, {**job_ref, "instance_id": "fixture", "workspace_id": WS,
                                             "project_id": PROJECT, "coordinator_id": COORDINATOR})
                if inner.error:
                    raise native.MailboxError("forbidden")
                return {"job_id": job_ref["job_id"], "latest_result_version": inner.version}

            version = 3
            error = False

        mailbox = JobReadOnly()
        with patch.object(native.Mailbox, "from_env", return_value=mailbox):
            source = self.new_source()
            self.assertEqual(source.poll()["hints"], ["mailbox:fixture-job:3"])
            mailbox.version = 2
            self.assertEqual(source.poll()["hints"], [])
            mailbox.version = 1
            self.assertEqual(source.poll()["pending"], ["mailbox:mailbox_version_regressed"])
            mailbox.error = True
            self.assertEqual(source.poll()["pending"], ["mailbox:forbidden"])
            with self.assertRaisesRegex(native.NativeSourceError, "verified_poll_required"):
                source.notify(MARKER)

    def test_notify_requires_current_poll_and_exact_on_scope_receipt(self):
        source = self.new_source()
        with self.assertRaisesRegex(native.NativeSourceError, "verified_poll_required"):
            source.notify(MARKER)
        source.poll()
        self.assertIsNone(source.notify(MARKER))
        self.assertIsNone(source.notify(MARKER))
        self.assertEqual(len(self.posted), 1)
        request = self.posted[0]
        self.assertEqual({key: request[key] for key in (
            "agent_id", "parent_comment_id", "kind", "mode", "expires_in_seconds", "on_timeout",
        )}, {"agent_id": COORDINATOR, "parent_comment_id": THREAD, "kind": "event", "mode": "once",
             "expires_in_seconds": 60, "on_timeout": "end"})
        payload = json.loads(request["instruction"].splitlines()[0])
        self.assertEqual({key: payload[key] for key in SCOPE}, SCOPE)
        self.assertEqual(payload["marker"], MARKER)
        self.assertIsNone(self.new_source().lookup(MARKER))
        self.begin_reminder_run()
        result = self.new_source().lookup(MARKER)
        self.assertEqual((result["marker"], result["wakeup_id"], result["run_id"], result["state"]),
                         (MARKER, RULE, REMINDER_RUN, "started"))
        self.runs[0]["agent_id"] = SUPPLIER
        with self.assertRaisesRegex(native.NativeSourceError, "wakeup_run_scope_unconfirmed"):
            self.new_source().lookup(MARKER)

    def test_lost_write_response_restarts_with_read_only_reconciliation(self):
        source = self.new_source()
        source.poll()
        self.lose_post = True
        with self.assertRaisesRegex(native.NativeSourceError, "multica:transport_error"):
            source.notify(MARKER)
        self.assertIsNone(self.new_source().lookup(MARKER))
        self.begin_reminder_run()
        self.assertEqual(self.new_source().lookup(MARKER)["run_id"], REMINDER_RUN)
        self.assertEqual(len(self.posted), 1)

    def test_mutated_source_or_copied_marker_cannot_authorize_send(self):
        source = self.new_source()
        source.poll()
        row = deepcopy(self.comments[1])
        self.comments[1]["content"] = "/note unblock.v1 " + json.dumps({**BASE_SNAPSHOT, "revision": 2})
        with self.assertRaisesRegex(native.NativeSourceError, "poll_snapshot_changed"):
            source.notify(MARKER)
        self.comments[1] = row
        self.rules.append({"id": RULE, "workspace_id": WS, "issue_id": ISSUE, "agent_id": SUPPLIER,
                           "parent_comment_id": THREAD, "enabled": False, "instruction": f"Copied {MARKER}"})
        with self.assertRaisesRegex(native.NativeSourceError, "wakeup_marker_conflict"):
            source.notify(MARKER)
        self.assertEqual(self.posted, [])

    def test_preflight_holds_without_consuming_the_attempt_when_the_run_ends(self):
        source = self.new_source()
        self.assertEqual(source.check_ready(), "verified_poll_required")
        source.poll()
        row = {"id": RUN, "workspace_id": WS, "issue_id": ISSUE, "agent_id": SUPPLIER, "status": "running"}
        self.runs.append(row)
        self.assertEqual(source.check_ready(), "issue_run_in_flight")
        self.assertEqual(self.posted, [])
        row["status"] = "completed"
        self.assertIsNone(source.check_ready())
        self.assertEqual(self.posted, [])
        self.assertIsNone(source.notify(MARKER))
        self.assertEqual(len(self.posted), 1)

    def test_real_wire_category_blocked_can_send_one_wakeup(self):
        self.issue["status"] = "blocked"
        self.statuses[0].update(key="blocked", category="blocked")
        source = self.new_source()
        source.poll()
        self.assertIsNone(source.check_ready())
        self.assertIsNone(source.notify(MARKER))
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.posted[0]["condition"]["value"], "blocked")

    def test_notification_holds_for_closed_card_active_rule_or_inflight_run(self):
        source = self.new_source()
        with patch.dict(self.statuses[0], {"category": "cancelled"}):
            source.poll()
            with self.assertRaisesRegex(native.NativeSourceError, "issue_closed_or_paused"):
                source.notify(MARKER)
        self.rules.append({"id": RULE, "workspace_id": WS, "issue_id": ISSUE, "agent_id": COORDINATOR,
                           "parent_comment_id": THREAD, "instruction": "Existing reminder", "enabled": True})
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_wakeup_already_active"):
            source.notify(MARKER)
        self.rules.clear()
        self.runs.append({"id": RUN, "workspace_id": WS, "issue_id": ISSUE,
                          "agent_id": SUPPLIER, "status": "queued"})
        with self.assertRaisesRegex(native.NativeSourceError, "issue_run_in_flight"):
            source.notify(MARKER)
        self.assertEqual(self.posted, [])

    def test_disabled_source_allows_read_only_recovery(self):
        self.registration["notifications_enabled"] = False
        source = self.new_source()
        self.assertEqual(source.poll()["hints"], [])
        with self.assertRaisesRegex(native.NativeSourceError, "notifications_disabled"):
            source.notify(MARKER)
        self.assertIsNone(source.lookup(MARKER))
        self.assertEqual(self.posted, [])


if __name__ == "__main__":
    unittest.main()
