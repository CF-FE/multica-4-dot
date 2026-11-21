import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from unblock.ledger import NotificationNotSent, reconcile, reconcile_existing


SCOPE = '[["instance","multica-a"],["workspace","cloud"],["project","one"],["issue","42"],["thread","9"]]'
CHECKPOINT = "round-7"


def verified_receipt(marker, number=1):
    return {
        "wakeup_id": f"00000000-0000-4000-8000-{number:012x}",
        "run_id": f"00000000-0000-4001-8000-{number:012x}",
        "marker": marker,
        "state": "started",
        "started_at": "2026-11-21T08:00:00Z",
    }


class UnblockLedgerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "unblock.sqlite3"
        self.sends = []
        self.lookups = []

    def send(self, marker):
        self.sends.append(marker)
        return verified_receipt(marker, len(self.sends))

    def lookup(self, marker):
        self.lookups.append(marker)
        return None

    def test_same_checkpoint_coalesces_replays_and_new_checkpoint_can_send(self):
        first = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        replay = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        next_round = reconcile(self.db, SCOPE, "round-8", self.send, self.lookup)
        late_signal = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)

        self.assertEqual(first, {"status": "confirmed", "marker": first["marker"],
                                 "receipt": verified_receipt(first["marker"])})
        self.assertEqual(first, replay)
        self.assertEqual(first, late_signal)
        self.assertNotEqual(first["marker"], next_round["marker"])
        self.assertEqual(self.sends, [first["marker"], next_round["marker"]])
        self.assertEqual(self.lookups, [])

    def test_scope_binds_every_registration_component(self):
        original = json.loads(SCOPE)
        registered_scopes = [original]
        for idx, (field, _) in enumerate(original):
            alternative = original.copy()
            alternative[idx] = [field, "different"]
            registered_scopes.append(alternative)

        for scope in registered_scopes:
            outcome = reconcile(self.db, json.dumps(scope), CHECKPOINT, self.send, self.lookup)
            self.assertEqual(outcome["status"], "confirmed")

        self.assertEqual(len(self.sends), len(registered_scopes))
        self.assertEqual(len(set(self.sends)), len(registered_scopes))

    def test_simultaneous_signals_can_only_send_once(self):
        sending = threading.Event()
        release = threading.Event()

        def slow_send(marker):
            self.sends.append(marker)
            sending.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test did not release the sender")
            return verified_receipt(marker)

        with ThreadPoolExecutor(max_workers=2) as pool:
            sender = pool.submit(reconcile, self.db, SCOPE, CHECKPOINT, slow_send, self.lookup)
            try:
                self.assertTrue(sending.wait(timeout=5))
                observer = pool.submit(reconcile, self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
                during_send = observer.result(timeout=5)
                self.assertEqual(during_send["status"], "unknown")
                self.assertIsNone(during_send["receipt"])
            finally:
                release.set()
            sent = sender.result(timeout=5)

        self.assertEqual(sent["status"], "confirmed")
        self.assertEqual(sent["marker"], during_send["marker"])
        self.assertEqual(self.sends, [sent["marker"]])
        self.assertEqual(self.lookups, [sent["marker"]])

    def test_permission_failure_and_empty_lookup_never_reopen_send(self):
        def denied_send(marker):
            self.sends.append(marker)
            raise PermissionError("fixture send denied")

        def denied_lookup(marker):
            self.lookups.append(marker)
            raise PermissionError("fixture lookup denied")

        first = reconcile(self.db, SCOPE, CHECKPOINT, denied_send, denied_lookup)
        second = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        third = reconcile(self.db, SCOPE, CHECKPOINT, self.send, denied_lookup)

        self.assertEqual(first, {"status": "unknown", "marker": first["marker"], "receipt": None,
                                 "reason": "lookup_failed"})
        self.assertEqual(second, {**first, "reason": "receipt_pending"})
        self.assertEqual(first, third)
        self.assertEqual(self.sends, [first["marker"]])
        self.assertIn(first["marker"], self.lookups)

    def test_only_an_explicit_pre_post_abort_allows_trying_same_marker_again(self):
        def appointment_unavailable(_):
            raise NotificationNotSent("coordinator_appointment_unconfirmed")

        first = reconcile(self.db, SCOPE, CHECKPOINT, appointment_unavailable, self.lookup)
        self.assertEqual(first, {"status": "deferred", "marker": first["marker"], "receipt": None,
                                 "reason": "coordinator_appointment_unconfirmed"})
        self.assertEqual(reconcile_existing(self.db, SCOPE, CHECKPOINT, self.lookup)["status"], "not_found")

        sent = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        self.assertEqual(sent["status"], "confirmed")
        self.assertEqual(sent["marker"], first["marker"])
        self.assertEqual(self.sends, [sent["marker"]])
        self.assertEqual(self.lookups, [])

    def test_pre_post_abort_preserves_receipt_observed_by_another_reader(self):
        def expire_with_observed_receipt(marker):
            recovered = reconcile_existing(self.db, SCOPE, CHECKPOINT, verified_receipt)
            self.assertEqual(recovered["receipt"], verified_receipt(marker))
            raise NotificationNotSent("coordinator_appointment_changed")

        first = reconcile(self.db, SCOPE, CHECKPOINT, expire_with_observed_receipt, self.lookup)
        self.assertEqual(first["status"], "confirmed")
        second = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        self.assertEqual(first, second)
        self.assertEqual(self.sends, [])

    def test_reconciliation_observes_pre_post_release_from_another_connection(self):
        claimed = threading.Event()
        looking_up = threading.Event()
        released = threading.Event()

        def abort_before_post(_):
            claimed.set()
            if not looking_up.wait(timeout=5):
                raise TimeoutError("observer did not start lookup")
            raise NotificationNotSent("coordinator_appointment_changed")

        def lookup_after_release(_):
            looking_up.set()
            if not released.wait(timeout=5):
                raise TimeoutError("sender did not release claim")
            return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            sender = pool.submit(reconcile, self.db, SCOPE, CHECKPOINT, abort_before_post, self.lookup)
            try:
                self.assertTrue(claimed.wait(timeout=5))
                observer = pool.submit(reconcile_existing, self.db, SCOPE, CHECKPOINT, lookup_after_release)
                deferred = sender.result(timeout=5)
                self.assertEqual(deferred["status"], "deferred")
            finally:
                released.set()
            self.assertEqual(observer.result(timeout=5), {"status": "not_found", "marker": None, "receipt": None})

        sent = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        self.assertEqual(sent["status"], "confirmed")
        self.assertEqual(sent["marker"], deferred["marker"])
        self.assertEqual(self.sends, [sent["marker"]])

    def test_lost_response_recovers_by_exact_marker(self):
        remote = {}

        def send_without_reply(marker):
            self.sends.append(marker)
            remote[marker] = verified_receipt(marker)
            return None

        first = reconcile(self.db, SCOPE, CHECKPOINT, send_without_reply, self.lookup)
        recovered = reconcile(self.db, SCOPE, CHECKPOINT, self.send, remote.get)
        cached = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)

        self.assertEqual(first["status"], "unknown")
        self.assertEqual(recovered, {"status": "confirmed", "marker": first["marker"],
                                     "receipt": verified_receipt(first["marker"])})
        self.assertEqual(recovered, cached)
        self.assertEqual(self.sends, [first["marker"]])

    def test_receipt_accepts_native_uuid_case_and_timestamp_offset(self):
        def send(marker):
            receipt = verified_receipt(marker, 10)
            receipt["wakeup_id"] = receipt["wakeup_id"].upper()
            receipt["started_at"] = "2026-11-21T16:00:00+08:00"
            return receipt

        result = reconcile(self.db, SCOPE, CHECKPOINT, send, self.lookup)

        self.assertEqual(result, {"status": "confirmed", "marker": result["marker"],
                                  "receipt": send(result["marker"])})

    def test_abrupt_sender_exit_keeps_durable_intent_for_restart(self):
        remote = self.root / "persisted-notification.json"
        sender = """
import json
import os
from pathlib import Path
import sys

from unblock.ledger import reconcile

db_path, scope, checkpoint, remote_path = sys.argv[1:]

def send_and_exit(marker):
    Path(remote_path).write_text(json.dumps({
        "marker": marker,
        "wakeup_id": "00000000-0000-4000-8000-000000000001",
        "run_id": "00000000-0000-4001-8000-000000000001",
        "state": "started",
        "started_at": "2026-11-21T08:00:00Z",
    }))
    os._exit(17)

reconcile(db_path, scope, checkpoint, send_and_exit, lambda _: None)
"""
        process = subprocess.run(
            [sys.executable, "-B", "-c", sender, str(self.db), SCOPE, CHECKPOINT, str(remote)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(process.returncode, 17, process.stderr)
        original_receipt = json.loads(remote.read_text())

        def lookup(marker):
            self.lookups.append(marker)
            if marker == original_receipt["marker"]:
                return original_receipt
            return None

        recovered = reconcile_existing(self.db, SCOPE, CHECKPOINT, lookup)

        self.assertEqual(recovered, {"status": "confirmed", "marker": original_receipt["marker"],
                                     "receipt": original_receipt})
        self.assertEqual(self.lookups, [original_receipt["marker"]])
        self.assertEqual(self.sends, [])

    def test_recovery_does_not_create_a_database_or_claim(self):
        not_found = {"status": "not_found", "marker": None, "receipt": None}

        self.assertEqual(reconcile_existing(self.db, SCOPE, CHECKPOINT, self.lookup), not_found)
        self.assertFalse(self.db.exists())
        sqlite3.connect(self.db).close()
        self.assertEqual(reconcile_existing(self.db, SCOPE, CHECKPOINT, self.lookup), not_found)

        existing = reconcile(self.db, SCOPE, CHECKPOINT, self.send, self.lookup)
        other_scope = SCOPE.replace('"cloud"', '"other"')
        self.assertEqual(reconcile_existing(self.db, other_scope, CHECKPOINT, self.lookup), not_found)
        self.assertEqual(reconcile_existing(self.db, SCOPE, "other-round", self.lookup), not_found)
        self.assertEqual(reconcile_existing(self.db, SCOPE, CHECKPOINT, self.lookup), existing)
        self.assertEqual(self.lookups, [])

        other = reconcile(self.db, other_scope, CHECKPOINT, self.send, self.lookup)
        self.assertEqual(other["status"], "confirmed")
        self.assertEqual(self.sends, [existing["marker"], other["marker"]])

    def test_unverified_callback_documents_never_become_confirmed(self):
        invalid_receipts = (
            lambda _: {},
            lambda _: verified_receipt("unblock.v1:other"),
            lambda marker: {**verified_receipt(marker), "wakeup_id": ""},
            lambda marker: {**verified_receipt(marker), "wakeup_id": "not-a-uuid"},
            lambda marker: {**verified_receipt(marker), "run_id": "not-a-uuid"},
            lambda marker: {**verified_receipt(marker), "state": "pending"},
            lambda marker: {**verified_receipt(marker), "started_at": "2026-11-21T08:00:00"},
            lambda marker: {**verified_receipt(marker), "started_at": "forever"},
        )
        for idx, invalid in enumerate(invalid_receipts):
            with self.subTest(idx=idx):
                checkpoint = f"invalid-{idx}"
                outcome = reconcile(self.db, SCOPE, checkpoint, invalid, invalid)
                self.assertEqual(outcome["status"], "unknown")
                self.assertIsNone(outcome["receipt"])
                self.assertEqual(outcome["reason"], "lookup_receipt_invalid")
                recovered = reconcile_existing(self.db, SCOPE, checkpoint, invalid)
                self.assertEqual(recovered["status"], "unknown")
                self.assertEqual(recovered["marker"], outcome["marker"])
                self.assertIsNone(recovered["receipt"])
                self.assertEqual(recovered["reason"], "lookup_receipt_invalid")

    def test_ephemeral_database_cannot_claim_send(self):
        for db_path in ("", ":memory:", b":memory:"):
            with self.subTest(db_path=db_path), self.assertRaises(ValueError):
                reconcile(db_path, SCOPE, CHECKPOINT, self.send, self.lookup)
        self.assertEqual(self.sends, [])


if __name__ == "__main__":
    unittest.main()
