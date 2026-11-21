"""Fixture-only verification of the v0.11.0 native REST boundary."""

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import json
import os
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from unblock import native
from unblock.__main__ import scope_key
from unblock.appointment import AppointmentScan
from unblock.ledger import reconcile, reconcile_existing


WS, PROJECT, ISSUE, THREAD, COORDINATOR, USER, SUPPLIER, SUMMARY, RUN, RULE, REMINDER_RUN = (
    str(UUID(int=value)) for value in range(1, 12)
)
MARKER = "unblock.v1:" + "a" * 64
ORIGIN = "http://127.0.0.1:8086"
MINUTE_ZERO = "2026-11-21T10:00:00Z"
MINUTE_ONE = "2026-11-21T10:01:00Z"
MINUTE_TWO = "2026-11-21T10:02:00Z"
MINUTE_THREE = "2026-11-21T10:03:00Z"
ISSUE_PATH = f"/api/issues/{ISSUE}"
THREAD_PATH = f"{ISSUE_PATH}/comments?thread={THREAD}"
ROOTS_PATH = f"{ISSUE_PATH}/comments?roots_only=true"
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
            "roles": {"coordinator": {"id": COORDINATOR, "appointment_ref": "fixture:appointment",
                                      "valid_from": "2020-01-01T00:00:00Z", "valid_until": None}},
        }
        self.config = f"Profile:      fixture\nserver_url:      {ORIGIN}\n"
        self.identity = {"id": USER}
        self.issue = {"id": ISSUE, "workspace_id": WS, "project_id": PROJECT, "status": "in_progress"}
        self.agent = {"id": COORDINATOR, "workspace_id": WS, "name": "Fixture agent",
                      "system_key": "mika", "archived_at": None}
        self.comments = [comment(THREAD, "original thread", parent=None, at=MINUTE_ZERO),
                         comment(SUMMARY, "/note unblock.v1 " + json.dumps(BASE_SNAPSHOT))]
        self.root_comments = [self.comments[0]]
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
        workspace = self.registration["workspace_id"]
        self.assertEqual(headers["Authorization"], "Bearer mul_fixture_only")
        self.assertEqual(headers.get("X-Workspace-ID"), None if path == "/api/me" else workspace)
        if method == "POST":
            self.assertEqual(path, RULES_PATH)
            body = json.loads(body)
            self.posted.append(body)
            rule = {
                **body, "id": RULE, "workspace_id": workspace, "issue_id": ISSUE, "created_by": USER,
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
            "/api/me": self.identity, f"/api/projects/{PROJECT}": {"id": PROJECT, "workspace_id": workspace},
            ISSUE_PATH: self.issue, f"/api/agents/{self.registration['coordinator_id']}": self.agent,
            THREAD_PATH: self.comments,
            ROOTS_PATH: self.root_comments,
            RUNS_PATH: self.runs, RULES_PATH: self.rules, RULE_RUNS_PATH: self.rule_runs,
            "/api/issue-statuses": {"statuses": self.statuses},
        }
        return FixtureResponse(fixtures[path], headers=self.response_headers.get(path))

    def new_source(self):
        return native.NativeSource(self.registration)

    def appoint(self, agent_id=COORDINATOR, *, generation="fixture-current", since=MINUTE_ZERO):
        self.registration["coordinator_id"] = self.agent["id"] = agent_id
        self.registration["roles"]["coordinator"]["id"] = agent_id
        self.registration["appointment_ssh_config"] = "/fixture/appointment-ssh.conf"
        appointment = {**{key: self.registration[key] for key in (
            "instance_id", "workspace_id", "coordinator_id",
        )}, "generation": generation, "confirmed_since": since}
        self.registration["_live_appointment"] = appointment
        return appointment

    def sign_summary(self, number, *, agent_id=COORDINATOR, posted=MINUTE_TWO, recorded=MINUTE_ONE):
        snapshot = {**BASE_SNAPSHOT, "coordinator_id": agent_id, "recorded_at": recorded}
        row = comment(str(UUID(int=number)), "/note unblock.v1 " + json.dumps(snapshot), author=agent_id, at=posted)
        self.comments.append(row)
        return row

    def use_cached_appointment(self, checked_at=MINUTE_TWO):
        self.appoint()
        self.registration["_appointment_cached"] = True
        self.registration["_appointment_checked_at"] = checked_at
        self.comments.pop()
        return self.sign_summary(51)

    def add_supplement(self, number, *, author=SUPPLIER, author_type="member", at=MINUTE_TWO, **scope):
        evidence = {**SCOPE, "checkpoint_id": "review-copy", "evidence_ref": "fixture://evidence", **scope}
        row = comment(str(UUID(int=number)), "/note unblock.evidence.v1 " + json.dumps(evidence),
                      author=author, author_type=author_type, at=at)
        self.comments.append(row)
        return row["id"]

    def add_handoff(self, number, *, author=SUPPLIER, author_type="member", at=MINUTE_TWO, **fields):
        handoff = {**SCOPE, "checkpoint_id": "review-copy", "evidence_ref": "fixture://patrol", **fields}
        row = comment(str(UUID(int=number)), "/note unblock.handoff.v1 " + json.dumps(handoff),
                      author=author, author_type=author_type, at=at, parent=None)
        self.root_comments.append(row)
        return row

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
            (self.agent, {"workspace_id": SUPPLIER}, "coordinator_changed"),
            (self.agent, {"archived_at": MINUTE_TWO}, "coordinator_changed"),
        ):
            with self.subTest(reason=reason), patch.dict(row, change):
                with self.assertRaises(native.NativeSourceError) as captured:
                    self.new_source().poll()
                self.assertEqual(captured.exception.code, reason)
        self.agent.pop("archived_at")
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_changed"):
            self.new_source().poll()

    def test_workspace_custom_coordinator_with_the_same_name_can_receive_a_reminder(self):
        different_workspace = str(UUID(int=23))
        self.registration["workspace_id"] = different_workspace
        for row in (self.issue, self.agent, self.statuses[0]):
            row["workspace_id"] = different_workspace
        self.agent.pop("system_key")
        self.comments[1]["content"] = "/note unblock.v1 " + json.dumps({
            **BASE_SNAPSHOT, "workspace_id": different_workspace,
        })
        source = self.new_source()
        self.assertEqual(source.poll()["summary_source"]["author_id"], COORDINATOR)
        self.assertIsNone(source.check_ready())
        source.notify(MARKER)
        self.assertEqual(len(self.posted), 1)
        self.assertEqual(self.posted[0]["agent_id"], COORDINATOR)

    def test_expired_coordinator_appointment_blocks_send(self):
        self.registration["roles"]["coordinator"]["valid_until"] = MINUTE_TWO
        source = self.new_source()
        source.poll()
        with patch.object(native, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat(MINUTE_TWO)
            self.assertEqual(source.check_ready(), "coordinator_appointment_inactive")
            with self.assertRaisesRegex(native.NativeSourceError, "coordinator_appointment_inactive"):
                source.notify(MARKER)
        self.assertEqual(self.posted, [])

    def test_closed_historical_binding_can_find_archived_coordinator_run(self):
        source = self.new_source()
        source.poll()
        source.notify(MARKER)
        self.begin_reminder_run()
        self.agent["archived_at"] = MINUTE_TWO
        self.registration["notifications_enabled"] = False
        historical = self.new_source()
        self.assertEqual(historical.lookup(MARKER)["run_id"], REMINDER_RUN)
        with self.assertRaisesRegex(native.NativeSourceError, "notifications_disabled"):
            historical.notify(MARKER)
        self.assertEqual(len(self.posted), 1)

    def test_current_appointment_requires_fresh_summary_even_when_former_agent_returns(self):
        self.appoint(generation="returned-coordinator", since=MINUTE_ONE)
        self.comments[1]["content"] = "/note unblock.v1 invalid historical body"
        self.sign_summary(51, recorded=MINUTE_ZERO)
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_summary_unconfirmed"):
            self.new_source().poll()
        new = self.sign_summary(52, posted=MINUTE_THREE, recorded=MINUTE_TWO)
        self.assertEqual(self.new_source().poll()["summary_source"]["comment_id"], new["id"])
        self.assertEqual(self.posted, [])

    def test_cached_appointment_requests_refresh_only_for_new_scoped_agent_summary(self):
        current = self.use_cached_appointment()
        self.sign_summary(52, agent_id=SUPPLIER)
        different = self.sign_summary(53, agent_id=SUPPLIER, posted=MINUTE_THREE, recorded=MINUTE_TWO)
        original_content = different["content"]
        wrong_scope = original_content.replace(PROJECT, "wrong-project")
        wrong_round = original_content.replace("review-copy", "another-round")
        with patch.object(native, "read_appointment", side_effect=AssertionError("poll must not dial")):
            for changes in (
                {"content": wrong_scope}, {"content": wrong_round}, {"author_id": USER},
                {"updated_at": MINUTE_TWO}, {"deleted_at": MINUTE_THREE},
                {"content": "/note unblock.v1 invalid"},
            ):
                with self.subTest(changes=changes), patch.dict(different, changes):
                    self.assertEqual(self.new_source().poll()["summary_source"]["comment_id"], current["id"])
            with self.assertRaisesRegex(native.NativeSourceError, "coordinator_refresh_required"):
                self.new_source().poll()
            with patch.dict(current, {"content": "/note unblock.v1 invalid cached incumbent snapshot"}):
                with self.assertRaisesRegex(native.NativeSourceError, "coordinator_refresh_required"):
                    self.new_source().poll()
            self.registration["_appointment_checked_at"] = MINUTE_THREE
            self.assertEqual(self.new_source().poll()["summary_source"]["comment_id"], current["id"])
            self.registration["_appointment_cached"] = False
            self.registration["_appointment_checked_at"] = MINUTE_TWO
            self.assertEqual(self.new_source().poll()["summary_source"]["comment_id"], current["id"])
        self.assertEqual(self.posted, [])

    def test_cached_appointment_with_missing_summary_only_refreshes_on_new_handoff(self):
        current = self.use_cached_appointment()
        self.comments.remove(current)
        self.registration["handoff_member_id"] = USER
        self.add_handoff(52, author=USER, coordinator_id=SUPPLIER)
        self.add_handoff(53, author=SUPPLIER, coordinator_id=SUPPLIER, at=MINUTE_THREE)
        self.add_handoff(54, author=USER, coordinator_id=SUPPLIER, at=MINUTE_THREE,
                         checkpoint_id="another-round")
        self.add_handoff(55, author=USER, coordinator_id="invalid", at=MINUTE_THREE)
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_summary_unconfirmed"):
            self.new_source().poll()
        self.add_handoff(56, author=USER, coordinator_id=SUPPLIER, at=MINUTE_THREE)
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_refresh_required"):
            self.new_source().poll()
        self.comments.append(current)
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_refresh_required"):
            self.new_source().poll()
        self.registration["_appointment_checked_at"] = MINUTE_THREE
        self.assertEqual(self.new_source().poll()["hints"], [])
        self.assertEqual(self.posted, [])

    def test_unavailable_appointment_cannot_use_static_agent_or_consume_claim(self):
        self.appoint()
        self.comments.pop()
        self.sign_summary(51)
        source = self.new_source()
        source.poll()
        with TemporaryDirectory() as folder:
            db = os.path.join(folder, "ledger.sqlite3")
            key, checkpoint = scope_key(self.registration), "review-copy"
            with patch.object(native, "read_appointment",
                              side_effect=native.AppointmentUnavailable("timeout")) as read:
                self.assertIsNone(source.check_ready())
                read.assert_not_called()
                deferred = reconcile(db, key, checkpoint, source.notify, source.lookup)
            read.assert_called_once_with(self.registration["appointment_ssh_config"], "fixture", WS)
            self.assertEqual(deferred["status"], "deferred")
            self.assertEqual(deferred["reason"], "coordinator_appointment_unconfirmed")
            self.assertEqual(reconcile_existing(db, key, checkpoint, source.lookup)["status"], "not_found")
            self.assertEqual(self.posted, [])
            recovered_source = native.NativeSource(self.registration, appointment_reader=AppointmentScan(db).refresh)
            recovered_source.poll()
            with patch("unblock.appointment.read_appointment", return_value=self.registration["_live_appointment"]):
                sent = reconcile(db, key, checkpoint, recovered_source.notify, recovered_source.lookup)
                replay = reconcile(db, key, checkpoint, recovered_source.notify, recovered_source.lookup)
            self.assertEqual([post["agent_id"] for post in self.posted], [COORDINATOR])
            self.assertEqual(sent["marker"], deferred["marker"])
            self.assertEqual(replay["marker"], sent["marker"])
        del self.registration["_live_appointment"]
        with self.assertRaisesRegex(native.NativeSourceError, "coordinator_appointment_unconfirmed"):
            self.new_source().poll()
        self.assertEqual(len(self.posted), 1)

    def test_handover_after_claim_can_send_once_to_new_agent_while_preserving_marker(self):
        appointment = self.appoint()
        self.comments.pop()
        self.sign_summary(51)
        source = self.new_source()
        source.poll()
        next_appointment = {**appointment, "coordinator_id": SUPPLIER, "generation": "new"}
        with TemporaryDirectory() as folder:
            db = os.path.join(folder, "ledger.sqlite3")
            key, checkpoint = scope_key(self.registration), "review-copy"
            with patch.object(native, "read_appointment", return_value=next_appointment) as read:
                self.assertIsNone(source.check_ready())
                read.assert_not_called()
                deferred = reconcile(db, key, checkpoint, source.notify, source.lookup)
            read.assert_called_once_with(self.registration["appointment_ssh_config"], "fixture", WS)
            self.assertEqual(deferred["status"], "deferred")
            self.assertEqual(deferred["reason"], "coordinator_appointment_changed")
            self.assertEqual(self.posted, [])
            self.appoint(SUPPLIER, generation="new")
            self.sign_summary(52, agent_id=SUPPLIER, posted=MINUTE_THREE, recorded=MINUTE_TWO)
            read = Mock(return_value=next_appointment)
            current = native.NativeSource(self.registration, appointment_reader=read)
            current.poll()
            with patch.object(native, "read_appointment", side_effect=AssertionError("use injected authority reader")):
                self.assertIsNone(current.check_ready())
                read.assert_not_called()
                sent = reconcile(db, key, checkpoint, current.notify, current.lookup)
                replay = reconcile(db, key, checkpoint, current.notify, current.lookup)
            read.assert_called_once_with(self.registration["appointment_ssh_config"], "fixture", WS)
        self.assertEqual(sent["status"], "unknown")
        self.assertEqual(sent["marker"], replay["marker"])
        self.assertEqual(sent["marker"], deferred["marker"])
        self.assertEqual([post["agent_id"] for post in self.posted], [SUPPLIER])

    def test_old_rule_holds_new_coordinator_and_recovery_reads_old_run_without_appointment(self):
        old_source = self.new_source()
        old_source.poll()
        with TemporaryDirectory() as folder:
            db = os.path.join(folder, "ledger.sqlite3")
            key, checkpoint = scope_key(self.registration), "review-copy"
            self.lose_post = True
            undelivered = reconcile(db, key, checkpoint, old_source.notify, old_source.lookup)
            self.assertEqual(undelivered["status"], "unknown")
            self.appoint(SUPPLIER, since=MINUTE_ONE)
            self.sign_summary(51, agent_id=SUPPLIER, posted=MINUTE_THREE, recorded=MINUTE_TWO)
            current = self.new_source()
            current.poll()
            self.assertEqual(current.check_ready(), "previous_coordinator_wakeup_active")
            self.begin_reminder_run()
            recovery_source = native.NativeSource({key: value for key, value in self.registration.items()
                                                   if key not in ("coordinator_id", "roles", "_live_appointment")},
                                                  recovery_only=True)
            with patch.object(native, "read_appointment", side_effect=AssertionError("lookup must be independent")):
                recovered = reconcile_existing(db, key, checkpoint, recovery_source.lookup)
            self.assertEqual(recovered["status"], "confirmed")
            self.assertEqual(recovered["receipt"]["coordinator_id"], COORDINATOR)
            self.assertEqual(recovered["receipt"]["run_id"], REMINDER_RUN)
            self.assertEqual(recovered["marker"], undelivered["marker"])
            self.assertEqual(recovery_source.check_ready(), "recovery_only_source")
            with self.assertRaisesRegex(native.NativeSourceError, "recovery_only_source"):
                recovery_source.notify(undelivered["marker"])
        self.assertEqual(len(self.posted), 1)

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

    def test_only_opted_in_fresh_g8_member_handoff_is_a_hint(self):
        self.add_handoff(12, author=USER)
        self.add_handoff(13, author_type="agent")
        self.add_handoff(14, at=MINUTE_ONE)
        self.add_handoff(15, checkpoint_id="different-round")
        self.add_handoff(16, thread_id=REMINDER_RUN)
        self.add_handoff(17)["updated_at"] = "2026-11-21T10:03:00Z"
        self.add_handoff(18)["deleted_at"] = MINUTE_TWO
        handoff = self.add_handoff(19, evidence_ref="fixture://contains-untrusted-data")

        self.assertEqual(self.new_source().poll()["hints"], [])
        self.assertNotIn(("GET", ROOTS_PATH), self.requests)
        self.registration["handoff_member_id"] = SUPPLIER
        observed = self.new_source().poll()
        self.assertEqual(observed["hints"], [f"patrol_handoff:{handoff['id']}"])
        self.assertEqual(observed["pending"], [])

    def test_partial_or_invalid_g8_handoff_source_fails_closed(self):
        self.registration["handoff_member_id"] = SUPPLIER
        source = self.new_source()
        handoff = self.add_handoff(12)
        for header in native._INCOMPLETE_COMMENTS:
            with self.subTest(header=header):
                self.response_headers[ROOTS_PATH] = {header: "fixture"}
                with self.assertRaisesRegex(native.NativeSourceError, "multica:incomplete_response"):
                    source.poll()
        self.response_headers.pop(ROOTS_PATH)
        for change, code in (
            ({"issue_id": PROJECT}, "handoff_comment_scope_mismatch"),
            ({"parent_id": THREAD}, "handoff_comment_not_top_level"),
            ({"content_truncated": True}, "handoff_comment_truncated"),
            ({"content": '/note unblock.handoff.v1 {"x":1,"x":2}'}, "invalid_handoff"),
            ({"content": '/note unblock.handoff.v1 {"extra":"field"}'}, "invalid_handoff_fields"),
        ):
            with self.subTest(code=code), patch.dict(handoff, change):
                with self.assertRaisesRegex(native.NativeSourceError, code):
                    source.poll()
        with self.assertRaisesRegex(native.NativeSourceError, "verified_poll_required"):
            source.notify(MARKER)
        self.assertEqual(self.posted, [])

    def test_handoff_is_rechecked_before_sending(self):
        self.registration["handoff_member_id"] = SUPPLIER
        handoff = self.add_handoff(12)
        source = self.new_source()
        self.assertEqual(source.poll()["hints"], [f"patrol_handoff:{handoff['id']}"])
        self.assertIsNone(source.check_ready())
        handoff["deleted_at"] = MINUTE_TWO
        self.assertEqual(source.check_ready(), "poll_snapshot_changed")
        with self.assertRaisesRegex(native.NativeSourceError, "poll_snapshot_changed"):
            source.notify(MARKER)
        self.assertEqual(self.posted, [])

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
