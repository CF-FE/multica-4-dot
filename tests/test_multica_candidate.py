import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_multica_candidate as candidate


def go_events(*events):
    return "\n".join(json.dumps({"Action": action, "Test": test}) for action, test in events)


class CandidateFixtureTests(unittest.TestCase):
    def test_source_checks_report_drift_and_unavailable_independently(self):
        paths = dict((path, "\n".join(markers)) for path, markers in candidate.SOURCE_RULES.values())
        paths[candidate.COMMENTS] = "func changed() {}"
        del paths[candidate.RUNS]
        self.assertEqual(candidate.source_checks(paths), {
            "registered_routes": "pass",
            "issue_scoped_run_handler": "unknown",
            "comment_silence_and_receipt_code": "fail",
        })

    def test_altered_source_snapshot_cannot_supply_fixed_source_evidence(self):
        version = {"commit": "test-commit", "source_sha256": {}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path, markers in candidate.SOURCE_RULES.values():
                data = "\n".join(markers).encode()
                version["source_sha256"][path] = hashlib.sha256(data).hexdigest()
                file = root / version["commit"] / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data + (b"\n" if path == candidate.COMMENTS else b""))
            checks, detail = candidate.check_sources(version, root)
        self.assertEqual(checks["comment_silence_and_receipt_code"], "unknown")
        self.assertEqual(checks["issue_scoped_run_handler"], "pass")
        self.assertIn("SHA-256 mismatch", detail)

    def test_native_result_requires_run_and_pass_for_every_expected_test(self):
        events = [(action, test) for test in candidate.NATIVE_TESTS for action in ("run", "pass")]
        actual, passed = candidate.native_results(go_events(*events), 0)
        self.assertTrue(passed)
        self.assertEqual(actual, dict.fromkeys(candidate.NATIVE_TESTS.values(), "pass"))

        for partial in (events[:-2], [*events[:-2], ("pass", events[-1][1])],
                        [*events[:-1], ("skip", events[-1][1])]):
            actual, passed = candidate.native_results(go_events(*partial), 0)
            self.assertFalse(passed)
            self.assertEqual(actual["normal_comment_receipt_and_run"], "unknown")

        actual, passed = candidate.native_results(go_events(*events[:-1], ("fail", events[-1][1])), 0)
        self.assertFalse(passed)
        self.assertEqual(actual["normal_comment_receipt_and_run"], "fail")
        self.assertFalse(candidate.native_results(go_events(*events), 1)[1])

    def test_go_testmain_exit_zero_without_witness_never_passes(self):
        actual, passed = candidate.native_results(
            '{"Action":"output","Output":"Skipping integration tests: database not reachable"}\n'
            '{"Action":"pass","Package":"example/server"}', 0,
        )
        self.assertFalse(passed)
        self.assertEqual(set(actual.values()), {"unknown"})

    def test_missing_local_socket_leaves_both_native_releases_unknown(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()) as stdout:
            socket_path = str(Path(temp) / "missing.sock")
            with patch.object(candidate, "command") as command:
                self.assertEqual(candidate.main(["--isolated", "--docker-socket", socket_path]), 2)
                command.assert_not_called()
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["evidence"], "native_source_router")
        self.assertEqual(report["release_image_compatibility"], "unknown")
        self.assertEqual([row["role"] for row in report["versions"]], ["baseline", "candidate"])
        for row in report["versions"]:
            self.assertEqual(row["status"], "not_run")
            self.assertEqual(set(row["checks"].values()), {"unknown"})

    def test_source_results_never_certify_release_images(self):
        matrix = dict.fromkeys(candidate.SOURCE_RULES, "pass")
        with patch.object(candidate, "check_sources", return_value=(matrix, "")), contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(candidate.main(["--source"]), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["evidence"], "fixed_source_inspection")
        self.assertEqual(report["release_image_compatibility"], "unknown")
        self.assertEqual([row["status"] for row in report["versions"]], ["pass", "pass"])


if __name__ == "__main__":
    unittest.main()
