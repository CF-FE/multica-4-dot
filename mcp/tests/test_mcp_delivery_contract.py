"""Offline acceptance for the dispatch ledger and its native adapter contract."""

import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from multica_backend.delivery import (
    DeliveryLedger,
    DispatchCommand,
    IssueReference,
    NewIssue,
    RequestConflict,
    UnverifiedIssue,
)


WORKSPACE, PROJECT, COORDINATOR, ISSUE, OTHER = [
    f"{digit:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa" for digit in range(1, 6)
]
PRINCIPAL = "dot:operator-1"
INSTANCE = "primary"
COMMAND = DispatchCommand(
    INSTANCE, WORKSPACE, PROJECT, COORDINATOR, new_issue=NewIssue("Verify reports", "todo", "Check the original.")
)
ISSUE_REF = IssueReference(INSTANCE, WORKSPACE, PROJECT, ISSUE)


class NativeFixture:
    instance_id = INSTANCE

    def __init__(self, issue=None):
        self.issue = issue
        self.creates = 0
        self.checks = 0

    def lookup(self, command, correlation):
        return self.issue

    def check_create(self, command):
        self.checks += 1

    def create_issue(self, command, correlation):
        self.creates += 1
        self.issue = ISSUE_REF
        return self.issue


class DeliveryContractTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "delivery.sqlite3"
        self.ledger = DeliveryLedger(self.path)

    def deliver(self, native, *, command=COMMAND, principal=PRINCIPAL, request_id="request-1"):
        return self.ledger.deliver(principal, request_id, command, native)

    def test_concurrent_same_request_claims_once(self):
        both_prepared = threading.Barrier(2, timeout=5)
        release_write = threading.Event()
        duplicate_returned = threading.Event()

        class RacingNative(NativeFixture):
            def check_create(self, command):
                both_prepared.wait()

            def create_issue(self, command, correlation):
                if not release_write.wait(timeout=5):
                    raise AssertionError("duplicate did not return before native write was released")
                return super().create_issue(command, correlation)

        native = RacingNative()

        def send():
            result = DeliveryLedger(self.path).deliver(PRINCIPAL, "race", COMMAND, native)
            if result.state == "unknown":
                duplicate_returned.set()
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(send) for _ in range(2)]
            try:
                self.assertTrue(duplicate_returned.wait(5))
            finally:
                release_write.set()
            states = {result.result(timeout=5).state for result in results}
        self.assertEqual(states, {"unknown", "confirmed"})
        self.assertEqual(native.creates, 1)
        self.assertEqual(self.ledger.get(PRINCIPAL, "race").issue, ISSUE_REF)

    def test_same_id_conflicts_on_changed_input_and_is_scoped_to_principal(self):
        native = NativeFixture()
        first = self.deliver(native)
        normalized = replace(
            COMMAND,
            workspace_id=WORKSPACE.upper(),
            new_issue=replace(COMMAND.new_issue, title=" Verify reports "),
        )
        self.assertEqual(self.deliver(native, command=normalized), first)
        with self.assertRaises(RequestConflict):
            self.deliver(native, command=replace(COMMAND, new_issue=NewIssue("Different title", "todo")))
        self.assertEqual(native.creates, 1)
        other = self.deliver(NativeFixture(), principal="dot:operator-2")
        self.assertNotEqual(first.correlation, other.correlation)

    def test_same_id_conflicts_if_instance_changes_with_identical_native_uuids(self):
        native = NativeFixture()
        self.ledger.accept(PRINCIPAL, "request-1", COMMAND)
        with self.assertRaises(RequestConflict):
            self.deliver(native, command=replace(COMMAND, instance_id="restored-copy"))
        self.assertEqual((native.checks, native.creates), (0, 0))

    def test_cross_instance_lookup_does_not_confirm_matching_uuids(self):
        native = NativeFixture(replace(ISSUE_REF, instance_id="restored-copy"))
        with self.assertRaises(UnverifiedIssue):
            self.deliver(native)
        self.assertEqual(self.ledger.get(PRINCIPAL, "request-1").state, "accepted")
        self.assertEqual((native.checks, native.creates), (0, 0))

    def test_wrong_instance_adapter_is_rejected_before_any_native_call(self):
        class WrongAdapter(NativeFixture):
            instance_id = "restored-copy"

            def lookup(self, command, correlation):
                raise AssertionError("read attempted through the wrong adapter")

        native = WrongAdapter()
        with self.assertRaises(UnverifiedIssue):
            self.deliver(native)
        self.assertEqual((native.checks, native.creates), (0, 0))

    def test_cross_instance_write_readback_leaves_the_send_unknown(self):
        class WrongInstance(NativeFixture):
            def create_issue(self, command, correlation):
                issue = super().create_issue(command, correlation)
                return replace(issue, instance_id="restored-copy")

        native = WrongInstance()
        with self.assertRaises(UnverifiedIssue):
            self.deliver(native)
        self.assertEqual(self.ledger.get(PRINCIPAL, "request-1").state, "unknown")
        self.assertEqual(self.deliver(native).issue, ISSUE_REF)
        self.assertEqual(native.creates, 1)

    def test_original_issue_is_reused_without_mutation(self):
        native = NativeFixture(ISSUE_REF)
        link = replace(COMMAND, new_issue=None, original_issue_id=ISSUE)
        result = self.deliver(native, command=link)
        self.assertEqual((result.state, result.issue), ("confirmed", ISSUE_REF))
        self.assertEqual((native.checks, native.creates), (0, 0))

    def test_absent_or_wrong_scope_original_issue_never_falls_back_to_create(self):
        for issue in (None, replace(ISSUE_REF, issue_id=OTHER), replace(ISSUE_REF, project_id=OTHER)):
            with self.subTest(issue=issue):
                link = replace(COMMAND, new_issue=None, original_issue_id=ISSUE)
                native = NativeFixture(issue)
                with self.assertRaises(UnverifiedIssue):
                    self.deliver(native, command=link)
                self.assertEqual((native.checks, native.creates), (0, 0))

    def test_create_request_adopts_an_already_correlated_native_issue(self):
        native = NativeFixture(ISSUE_REF)
        result = self.deliver(native)
        self.assertEqual((result.state, result.issue), ("confirmed", ISSUE_REF))
        self.assertEqual((native.checks, native.creates), (0, 0))

    def test_failed_preflight_remains_accepted_and_can_recover(self):
        class RefusedNative(NativeFixture):
            def check_create(self, command):
                raise PermissionError("the frozen coordinator no longer owns the role")

        native = RefusedNative()
        with self.assertRaises(PermissionError):
            self.deliver(native)
        self.assertEqual(self.ledger.get(PRINCIPAL, "request-1").state, "accepted")
        self.assertEqual(native.creates, 0)
        self.assertEqual(self.deliver(NativeFixture()).state, "confirmed")

    def test_pending_enumeration_is_bounded_and_scoped_to_its_principal(self):
        for request_id in ("c", "a", "b"):
            self.ledger.accept(PRINCIPAL, request_id, COMMAND)
        self.ledger.accept("other-principal", "aa", COMMAND)
        self.deliver(NativeFixture(), request_id="b")

        self.assertEqual(self.ledger.list_pending(PRINCIPAL, limit=1), ("a",))
        self.assertEqual(self.ledger.list_pending(PRINCIPAL, after_request_id="a"), ("c",))
        self.assertEqual(self.ledger.list_pending("other-principal"), ("aa",))
        self.assertIsNone(self.ledger.get_command("other-principal", "a"))
        self.assertIsNone(self.ledger.get_command(PRINCIPAL, "b"))
        with self.assertRaises(ValueError):
            self.ledger.list_pending(PRINCIPAL, limit=101)

    def _run_child(self, body):
        setup = f"""
import os
import sys
from pathlib import Path
from multica_backend.delivery import DeliveryLedger, DispatchCommand, NewIssue

path = Path(sys.argv[1])
ledger = DeliveryLedger(path)
principal = {PRINCIPAL!r}
command = DispatchCommand({INSTANCE!r}, {WORKSPACE!r}, {PROJECT!r}, {COORDINATOR!r},
                          new_issue=NewIssue("Verify reports", "todo", "Check the original."))
"""
        return subprocess.run(
            [sys.executable, "-B", "-c", setup + body, str(self.path)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            timeout=10,
        )

    def test_process_exit_after_accept_leaves_the_original_request_sendable(self):
        child = self._run_child("""
ledger.accept(principal, "request-1", command)
os._exit(24)
""")
        self.assertEqual(child.returncode, 24, child.stderr.decode())
        self.assertEqual(self.ledger.get(PRINCIPAL, "request-1").state, "accepted")
        self.ledger = DeliveryLedger(self.path)
        native = NativeFixture()
        pending_ids = self.ledger.list_pending(PRINCIPAL)
        self.assertEqual(pending_ids, ("request-1",))
        restored = self.ledger.get_command(PRINCIPAL, pending_ids[0])
        self.assertEqual(restored, COMMAND)
        self.assertEqual(self.ledger.deliver(PRINCIPAL, pending_ids[0], restored, native).state, "confirmed")
        self.assertEqual(self.ledger.list_pending(PRINCIPAL), ())
        self.assertEqual(native.creates, 1)

    def test_timeout_then_restart_only_reconciles_even_if_lookup_is_empty(self):
        child = self._run_child("""
class Native:
    instance_id = command.instance_id

    def lookup(self, command, correlation):
        return None

    def check_create(self, command):
        pass

    def create_issue(self, command, correlation):
        path.with_suffix(".native").write_text(correlation)
        raise TimeoutError("native write committed and reply was lost")

try:
    ledger.deliver(principal, "request-1", command, Native())
except TimeoutError:
    os._exit(25)
""")
        self.assertEqual(child.returncode, 25, child.stderr.decode())
        self.ledger = DeliveryLedger(self.path)
        native = NativeFixture()
        self.assertEqual(self.ledger.list_pending(PRINCIPAL), ())
        self.assertEqual(self.ledger.list_pending(PRINCIPAL, state="unknown"), ("request-1",))
        restored = self.ledger.get_command(PRINCIPAL, "request-1")
        uncertain = self.ledger.deliver(PRINCIPAL, "request-1", restored, native)
        self.assertEqual(uncertain.state, "unknown")
        self.assertEqual(native.creates, 0)
        self.assertEqual(self.path.with_suffix(".native").read_text(), uncertain.correlation)
        native.issue = ISSUE_REF
        self.assertEqual(self.ledger.deliver(PRINCIPAL, "request-1", restored, native).issue, ISSUE_REF)
        self.assertIsNone(self.ledger.get_command(PRINCIPAL, "request-1"))
        self.assertEqual(native.creates, 0)

    def test_crash_after_claim_before_network_is_quarantined(self):
        child = self._run_child("""
class Native:
    instance_id = command.instance_id

    def lookup(self, command, correlation):
        return None

    def check_create(self, command):
        pass

    def create_issue(self, command, correlation):
        os._exit(26)

ledger.deliver(principal, "request-1", command, Native())
""")
        self.assertEqual(child.returncode, 26, child.stderr.decode())
        self.ledger = DeliveryLedger(self.path)
        native = NativeFixture()
        self.assertEqual(self.deliver(native).state, "unknown")
        self.assertEqual(native.creates, 0)


if __name__ == "__main__":
    unittest.main()
