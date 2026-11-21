import copy
import json
from datetime import datetime
from pathlib import Path
import unittest

from unblock.model import assess


DOC = Path(__file__).resolve().parents[1] / "docs" / "unblock-record-format.md"


def at(hour):
    return f"2026-11-21T{hour:02d}:00:00+08:00"


class UnblockModelTest(unittest.TestCase):
    def setUp(self):
        example = json.loads(DOC.read_text().split("```json\n", 1)[1].split("\n```", 1)[0])
        self.reg, self.snap = example["registration"], example["snapshot"]

    def role(self, role):
        return self.reg["roles"][role]["id"]

    def add_role(self, role):
        self.reg["roles"][role] = {
            "id": f"test-{role}", "name": role, "appointment_ref": f"fixture:{role}",
            "valid_from": at(10), "valid_until": None,
        }

    def record(self, role, hour=13, **fields):
        scope = {key: self.reg[key] for key in ("instance_id", "workspace_id", "project_id", "issue_id")}
        return {"ref": f"fixture:{role}", "actor_id": self.role(role), "at": at(hour), "source_scope": scope, **fields}

    def target_fields(self):
        target = self.snap["target"]
        return {"target_id": target["id"], "target_version": target["version"]}

    def action_receipt(self, role, hour=13, **fields):
        receipt = self.record(role, hour, **self.target_fields(), checkpoint_id=self.snap["checkpoint_id"],
                              step=self.snap["target"]["step"], **fields)
        receipt["source_scope"]["thread_id"] = self.snap["thread_id"]
        return receipt

    def all_gates(self):
        for kind in ("business", "isolation"):
            self.add_role(kind)
            self.snap["evidence"][kind] = self.record(
                kind, **self.target_fields(), result="confirmed", valid_until=at(18)
            )

    def recovery(self, verdict=None, scope="first_item"):
        self.all_gates()
        self.snap["recorded_at"] = at(15)
        self.snap["execution"] = self.action_receipt(
            "project_lead", 14, run_id="run-1", artifact_id="artifact-1",
        )
        if verdict:
            self.snap["acceptance"] = self.action_receipt(
                "acceptor", 15, run_id="run-1", artifact_id="artifact-1",
                scope=scope, result=verdict,
            )

    def g8_request(self):
        self.snap["g8_request"] = self.action_receipt(
            "coordinator", request_id="request-1", read_ack_ref="fixture:read-ack",
        )

    def assess(self, hour=14):
        return assess(self.reg, self.snap, datetime.fromisoformat(at(hour)))

    def test_technical_evidence_preserves_partial_progress_and_contact_is_only_a_lead(self):
        result = self.assess()
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["next_action"], "request_g8_review")
        self.assertIs(result["g8_pending"], True)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["checkpoint_id"], "first-copy")
        self.assertEqual(result["evidence"]["technical"]["status"], "confirmed")
        self.assertEqual(result["evidence"]["business"]["status"], "missing")
        self.assertIsNone(result["evidence"]["isolation"]["authority"])
        self.assertEqual(result["evidence"]["isolation"]["contact"]["name"], "入口联系人")

    def test_running_or_unknown_requires_reconciliation_even_with_gates(self):
        self.all_gates()
        for activity in ("in_flight", "unknown"):
            with self.subTest(activity=activity):
                self.snap["activity"] = activity
                result = self.assess()
                self.assertEqual(result["next_action"], "reconcile_activity")
                self.assertEqual(result["state"], "blocked")

    def test_assignment_or_run_without_pickup_needs_original_receipt(self):
        self.all_gates()
        self.snap.pop("pickup")
        result = self.assess()
        self.assertEqual(result["state"], "awaiting_pickup")
        self.assertEqual(result["next_action"], "reconcile_pickup")

    def test_original_pickup_cannot_sign_for_the_next_action_on_the_same_issue(self):
        self.snap["target"]["step"] = "选择准备项"
        self.snap["pickup"] = self.action_receipt("project_lead", ref="fixture:selection-accepted")
        previous = copy.deepcopy(self.snap)
        self.assertEqual(self.assess()["pickup_ref"], "fixture:selection-accepted")
        self.reg.pop("checkpoint_id")
        self.snap.update(checkpoint_id="review-P089", revision=2)
        self.snap["target"].update(id="P089", version="subtitle-v2", step="核对原音登记与字幕片段")
        self.snap["evidence"]["technical"].update(self.target_fields())
        self.recovery("accepted")
        waiting = self.assess(15)
        self.assertEqual(waiting["state"], "awaiting_pickup")
        self.assertIsNone(waiting["pickup_ref"])
        self.assertEqual(waiting["recorded_pickup_ref"], previous["pickup"]["ref"])
        self.assertIsNone(waiting["accepted_scope"])
        self.assertEqual(self.snap["pickup"], previous["pickup"])
        self.snap["pickup"] = self.action_receipt("project_lead", ref="fixture:p089-accepted")
        current = self.assess(15)
        self.assertEqual(current["state"], "recovered")
        self.assertEqual(current["pickup_ref"], "fixture:p089-accepted")
        self.assertEqual(current["accepted_scope"], "first_item")

    def test_pickup_requires_a_matching_action_original_thread_target_and_version(self):
        for changed in ({"checkpoint_id": "old"}, {"step": "别的动作"}, {"target_id": "C001"},
                        {"target_version": "older"}, {"actor_id": self.role("coordinator")}):
            with self.subTest(changed=changed):
                self.snap["pickup"] = {**self.action_receipt("project_lead"), **changed}
                self.assertEqual(self.assess()["state"], "awaiting_pickup")
        self.snap["pickup"] = self.action_receipt("project_lead")
        self.snap["pickup"]["source_scope"]["thread_id"] = "other-branch"
        self.assertIsNone(self.assess()["pickup_ref"])
        self.snap["pickup"] = self.record("project_lead")
        self.assertIsNone(self.assess()["pickup_ref"])
        self.assertEqual(self.assess()["recorded_pickup_ref"], "fixture:project_lead")

    def test_request_receipt_from_named_executor_is_independent_of_coordinator_receipt(self):
        self.snap["target"].update(request_id="req-P089", executor_id="worker-7")
        receipt = self.action_receipt("coordinator")
        receipt.pop("checkpoint_id")
        receipt.pop("step")
        receipt["request_id"] = "req-P089"
        self.snap["pickup"] = receipt
        self.assertIsNone(self.assess()["pickup_ref"])
        receipt["actor_id"] = "worker-7"
        self.assertEqual(self.assess()["pickup_status"], "accepted")
        receipt["request_id"] = "req-select"
        self.assertIsNone(self.assess()["pickup_ref"])
        receipt["checkpoint_id"] = self.snap["checkpoint_id"]
        receipt["step"] = self.snap["target"]["step"]
        self.assertIsNone(self.assess()["pickup_ref"])  # Supplied identifiers disagree.
        del receipt["request_id"]
        self.assertEqual(self.assess()["pickup_status"], "accepted")
        self.snap["target"]["executor_id"] = None
        receipt["request_id"] = "req-P089"
        self.assertEqual(self.assess()["owner_id"], self.role("coordinator"))
        self.assertIsNone(self.assess()["executor_id"])
        self.assertIsNone(self.assess()["pickup_ref"])

    def test_execution_from_a_previous_action_does_not_hide_the_new_handoff(self):
        self.recovery("accepted")
        self.assertEqual(self.assess(15)["state"], "recovered")
        self.snap["target"]["step"] = "核对 P089 的片段版本"
        result = self.assess(15)
        self.assertEqual(result["state"], "awaiting_pickup")
        self.assertEqual(result["next_action"], "reconcile_pickup")
        self.assertIsNone(result["accepted_scope"])
        self.assertIn("execution", self.snap)

    def test_elapsed_check_and_elapsed_decision_are_distinct(self):
        for kind in ("business", "isolation"):
            self.add_role(kind)
        self.assertEqual(self.assess(14)["next_action"], "collect_evidence")
        self.assertEqual(self.assess(15)["next_action"], "recheck_evidence")
        result = self.assess(16)
        self.assertEqual(result["next_action"], "request_g8_review")
        self.assertTrue(result["g8_pending"])

    def test_one_custom_required_gate_needs_only_its_own_authority(self):
        self.reg["required_evidence"] = ["data_version"]
        self.add_role("data_version")
        self.snap.pop("contacts")
        self.snap["evidence"] = {
            "data_version": self.record(
                "data_version", **self.target_fields(), result="confirmed", valid_until=at(18),
            )
        }
        result = self.assess()
        self.assertEqual(list(result["evidence"]), ["data_version"])
        self.assertEqual(result["next_action"], "verify_and_resume")
        self.assertFalse(result["g8_pending"])
        for invalid in ([], ["duplicate", "duplicate"], ["coordinator"], ["../../bad"], "data_version"):
            with self.subTest(invalid=invalid):
                self.reg["required_evidence"] = invalid
                with self.assertRaisesRegex(ValueError, "required_evidence"):
                    self.assess()

    def test_ack_keeps_coordinator_tracking_until_exact_g8_acceptance(self):
        self.g8_request()
        self.assertEqual(self.assess()["next_action"], "reconcile_g8_pickup")
        self.assertEqual(self.assess()["owner_id"], self.role("coordinator"))
        self.snap["g8_acceptance"] = self.record(
            "g8", request_id="request-1", next_owner_id=self.role("project_lead"), next_check_at=at(17),
        )
        result = self.assess()
        self.assertIs(result["g8_pending"], False)
        self.assertEqual(result["g8_status"], "accepted")
        self.assertEqual(result["next_action"], "follow_g8_plan")
        self.assertEqual(result["owner_id"], self.role("project_lead"))

    def test_g8_receipt_for_other_request_cannot_transfer_responsibility(self):
        self.g8_request()
        self.snap["g8_acceptance"] = self.record(
            "g8", request_id="another-request", next_owner_id=self.role("project_lead"), next_check_at=at(17),
        )
        with self.assertRaisesRegex(ValueError, "g8_acceptance.request_id"):
            self.assess()

    def test_event_only_g8_pickup_with_no_read_ack_disarms_old_due_time(self):
        self.g8_request()
        self.snap["g8_request"].pop("read_ack_ref")
        self.snap["g8_acceptance"] = self.record(
            "g8", request_id="request-1", next_owner_id=self.role("project_lead"), next_check_event="rule-published",
        )
        result = self.assess(16)
        self.assertEqual(result["g8_status"], "accepted")
        self.assertIs(result["g8_pending"], False)
        self.assertIs(result["checkpoint_due"], False)
        self.assertEqual(result["g8_next_check_event"], "rule-published")
        self.assertEqual(result["next_action"], "follow_g8_plan")
        self.snap["g8_acceptance"]["next_check_at"] = at(17)
        self.assertFalse(self.assess(16)["checkpoint_due"])
        self.assertTrue(self.assess(17)["checkpoint_due"])
        self.assertEqual(self.assess(17)["next_action"], "recheck_g8_plan")

    def test_previous_g8_handover_keeps_its_history_and_cannot_suppress_new_due_check(self):
        self.g8_request()
        self.snap["g8_acceptance"] = self.record(
            "g8", request_id="request-1", next_owner_id=self.role("project_lead"), next_check_event="old-confirmation")
        self.assertTrue(self.assess()["g8_acceptance_ref"])
        self.snap["target"].update(id="P089", step="核对原音登记", version="v2")
        self.snap["next_check_event"] = "P089 原音登记已回证"
        result = self.assess(16)
        self.assertIsNone(result["g8_acceptance_ref"])
        self.assertTrue(result["checkpoint_due"])
        self.assertEqual(result["next_check_event"], self.snap["next_check_event"])
        self.assertIn("g8_acceptance", self.snap)

    def test_g8_acceptance_requires_time_or_event(self):
        self.g8_request()
        self.snap["g8_acceptance"] = self.record(
            "g8", request_id="request-1", next_owner_id=self.role("project_lead"),
        )
        with self.assertRaisesRegex(ValueError, "next_check_at or next_check_event"):
            self.assess()

    def test_valid_gates_allow_recommendation_and_do_not_record_execution(self):
        self.all_gates()
        result = self.assess()
        self.assertEqual(result["next_action"], "verify_and_resume")
        self.assertEqual(result["state"], "blocked")
        self.assertIsNone(result["execution_ref"])

    def test_expired_evidence_or_role_and_old_target_keep_resume_blocked(self):
        self.all_gates()
        for field, value, status in (
            ("valid_until", at(14), "expired"),
            ("target_version", "old", "target_mismatch"),
            ("actor_id", "other", "authority_unverified"),
            ("result", "rejected", "rejected"),
        ):
            with self.subTest(field=field):
                old = self.snap["evidence"]["isolation"][field]
                self.snap["evidence"]["isolation"][field] = value
                result = self.assess()
                self.assertEqual(result["evidence"]["isolation"]["status"], status)
                self.assertNotEqual(result["next_action"], "verify_and_resume")
                self.snap["evidence"]["isolation"][field] = old
        self.reg["roles"]["isolation"]["valid_until"] = at(14)
        self.assertEqual(self.assess()["evidence"]["isolation"]["status"], "authority_unverified")

    def test_original_execution_advances_to_acceptance_even_if_permission_has_since_expired(self):
        self.recovery()
        result = self.assess(19)
        self.assertEqual(result["state"], "recovered")
        self.assertEqual(result["next_action"], "seek_acceptance")
        self.assertEqual(result["execution_ref"], "fixture:project_lead")
        self.assertFalse(result["g8_pending"])

    def test_execution_without_gates_at_execution_time_is_retained_but_not_confirmed_recovery(self):
        self.recovery()
        self.snap["evidence"]["business"]["at"] = at(15)
        result = self.assess(15)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["next_action"], "reconcile_execution")
        self.assertEqual(result["execution_ref"], "fixture:project_lead")

    def test_first_item_pass_never_implies_issue_acceptance(self):
        self.recovery("accepted")
        result = self.assess(15)
        self.assertEqual(result["next_action"], "return_to_delivery")
        self.assertEqual(result["accepted_scope"], "first_item")
        self.assertFalse(result["issue_accepted"])
        self.snap["target"]["acceptance_scope"] = "issue"
        result = self.assess(15)
        self.assertEqual(result["next_action"], "seek_acceptance")
        self.assertFalse(result["issue_accepted"])

    def test_broader_acceptance_cannot_be_attributed_to_first_item_target(self):
        self.recovery("accepted", "issue")
        result = self.assess(15)
        self.assertEqual(result["next_action"], "seek_acceptance")
        self.assertIsNone(result["accepted_scope"])
        self.assertFalse(result["issue_accepted"])

    def test_only_matching_designated_acceptor_can_accept_issue(self):
        self.recovery("accepted", "issue")
        self.snap["target"]["acceptance_scope"] = "issue"
        self.assertTrue(self.assess(15)["issue_accepted"])
        for field, wrong in (
            ("actor_id", self.role("project_lead")), ("artifact_id", "other"), ("run_id", "other"),
        ):
            with self.subTest(field=field):
                initial = self.snap["acceptance"][field]
                self.snap["acceptance"][field] = wrong
                self.assertFalse(self.assess(15)["issue_accepted"])
                self.snap["acceptance"][field] = initial

    def test_rejected_acceptance_routes_to_scoped_rework(self):
        self.recovery("rejected")
        result = self.assess(15)
        self.assertEqual(result["state"], "recovered")
        self.assertEqual(result["next_action"], "review_affected_scope")

    def test_formal_pause_has_priority_and_suppresses_g8_and_reminder(self):
        self.g8_request()
        self.add_role("disposition")
        self.snap["activity"] = "in_flight"
        self.snap["disposition"] = self.record(
            "disposition", **self.target_fields(), status="paused",
            reason="外部输入暂停", resume_condition="补齐输入",
        )
        result = self.assess()
        self.assertEqual(result["next_action"], "hold")
        self.assertEqual(result["disposition"], "paused")
        self.assertFalse(result["g8_pending"])
        self.assertFalse(result["notification_open"])

    def test_cancellation_keeps_a_due_checkpoint_quiet(self):
        self.add_role("disposition")
        self.snap["disposition"] = self.record(
            "disposition", **self.target_fields(), status="cancelled", reason="原委托取消",
        )
        result = self.assess(16)
        self.assertEqual(result["next_action"], "close_cancelled")
        self.assertTrue(result["checkpoint_due"])
        self.assertFalse(result["notification_open"])

    def test_mailbox_request_preserves_the_original_job_and_version(self):
        self.reg["mailbox"] = {"job_id": "job-1"}
        self.snap["mailbox_result_version"] = 17
        self.g8_request()
        self.snap["g8_request"]["job_id"] = "job-1"
        self.assertTrue(self.assess()["g8_pending"])
        self.snap["g8_request"]["job_id"] = "job-2"
        with self.assertRaisesRegex(ValueError, "g8_request.job_id"):
            self.assess()

    def test_malformed_or_cross_scope_input_is_rejected(self):
        for key, invalid in (
            ("revision", True), ("revision", 0), ("thread_id", "other"),
            ("checkpoint_id", "other"), ("due_at", "2026-11-21T15:00:00"),
            ("recorded_at", at(23)), ("activity", "completed"),
        ):
            with self.subTest(key=key):
                altered = dict(self.snap, **{key: invalid})
                with self.assertRaisesRegex(ValueError, key):
                    assess(self.reg, altered, datetime.fromisoformat(at(14)))
        altered = copy.deepcopy(self.snap)
        altered["evidence"]["technical"]["source_scope"]["project_id"] = "other"
        with self.assertRaisesRegex(ValueError, "source_scope.project_id"):
            assess(self.reg, altered, datetime.fromisoformat(at(14)))
        with self.assertRaisesRegex(ValueError, "now"):
            assess(self.reg, self.snap, datetime(2026, 11, 21))

    def test_current_signed_checkpoint_can_advance_when_registration_is_unpinned(self):
        self.snap["checkpoint_id"] = "new-round"
        with self.assertRaisesRegex(ValueError, "checkpoint_id"):
            self.assess()
        self.reg.pop("checkpoint_id")
        self.assertEqual(self.assess()["checkpoint_id"], "new-round")
        self.snap["checkpoint_id"] = ""
        with self.assertRaisesRegex(ValueError, "checkpoint_id"):
            self.assess()


if __name__ == "__main__":
    unittest.main()
