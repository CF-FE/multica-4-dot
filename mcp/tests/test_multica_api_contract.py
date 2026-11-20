"""Exercise the pinned read contract using synthetic records over loopback."""

from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
import unittest
from unittest import mock
from uuid import UUID

from multica_backend.multica_api import MulticaAPI, MulticaAPIError


ROOT = Path(__file__).resolve().parents[2]
USER, WORKSPACE, PROJECT, ISSUE, RUN, OTHER_RUN, OTHER = (str(UUID(int=i)) for i in range(1, 8))
TOKEN = "mul_synthetic_contract_token"
SECRET = "synthetic-private-response-body"
ME_PATH = "/api/me"
PROJECT_PATH = f"/api/projects/{PROJECT}"
ISSUE_PATH = f"/api/issues/{ISSUE}"
RUNS_PATH = ISSUE_PATH + "/task-runs?scope=issue&view=timeline"


def run_row(run_id=RUN, **overrides):
    return {
        "id": run_id, "issue_id": ISSUE, "workspace_id": WORKSPACE,
        "status": "completed", "completed_at": "2026-11-19T12:00:00Z",
        "error": SECRET, "result": {"credential": TOKEN}, **overrides,
    }


def replies():
    return {
        ME_PATH: (200, {"id": USER, "email": SECRET}),
        PROJECT_PATH: (200, {"id": PROJECT, "workspace_id": WORKSPACE, "description": SECRET}),
        ISSUE_PATH: (200, {"id": ISSUE, "workspace_id": WORKSPACE, "project_id": PROJECT,
                           "status": "custom_status", "metadata": {"secret": TOKEN}}),
        RUNS_PATH: (200, [run_row(OTHER_RUN, status="running", completed_at=None), run_row()]),
    }


@contextmanager
def fixture(responses):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.reply()

        def do_POST(self):
            self.reply()

        def reply(self):
            requests.append((self.command, self.path, self.headers.get("Authorization"),
                             self.headers.get("X-Workspace-ID")))
            status, body = responses.get(self.path, (404, {"private": SECRET}))
            location = body if 300 <= status < 400 else None
            encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", requests
        finally:
            server.shutdown()
            thread.join()


def client(origin, **overrides):
    return MulticaAPI(**{
        "origin": origin, "token": TOKEN, "expected_user_id": USER,
        "workspace_id": WORKSPACE, "project_id": PROJECT, **overrides,
    })


def invoke_cli(*args, token=None):
    env = os.environ.copy()
    env.pop("MULTICA_CONTRACT_TOKEN", None)
    if token is not None:
        env["MULTICA_CONTRACT_TOKEN"] = token
    return subprocess.run(
        [sys.executable, "-B", str(ROOT / "scripts/check_multica_contract.py"), *args],
        capture_output=True, text=True, env=env, cwd=ROOT.parent, timeout=10,
    )


def live_args(origin):
    return ["--live", "--origin", origin, "--expected-user-id", USER, "--workspace-id", WORKSPACE,
            "--project-id", PROJECT, "--issue-id", ISSUE, "--run-id", RUN]


class MulticaAPIContractTests(unittest.TestCase):
    def test_projects_issues_and_exact_run_are_read_with_the_configured_identity_and_scope(self):
        with fixture(replies()) as (origin, requests):
            api = client(origin)
            run = api.get_run(ISSUE, RUN)
            self.assertEqual((run.id, run.issue_id, run.workspace_id, run.project_id), (RUN, ISSUE, WORKSPACE, PROJECT))
            self.assertEqual((run.status, run.completed_at), ("completed", "2026-11-19T12:00:00Z"))
            self.assertNotIn(SECRET, repr(run))
            self.assertNotIn(TOKEN, repr(run))
            self.assertEqual(requests, [
                ("GET", ME_PATH, f"Bearer {TOKEN}", None),
                *(("GET", path, f"Bearer {TOKEN}", WORKSPACE) for path in (PROJECT_PATH, ISSUE_PATH, RUNS_PATH)),
            ])
            self.assertEqual(api.get_project().id, PROJECT)
            self.assertEqual(api.get_issue(ISSUE).status, "custom_status")
            self.assertEqual([row.id for row in api.list_issue_runs(ISSUE)], [OTHER_RUN, RUN])

    def test_stops_on_identity_or_scope_mismatch_before_reading_the_next_resource(self):
        cases = [
            (ME_PATH, {"id": OTHER}, "identity", "identity_mismatch", 1),
            (PROJECT_PATH, {"id": PROJECT, "workspace_id": OTHER}, "project", "scope_mismatch", 2),
            (ISSUE_PATH, {**replies()[ISSUE_PATH][1], "project_id": OTHER}, "issue", "scope_mismatch", 3),
            (ISSUE_PATH, {**replies()[ISSUE_PATH][1], "project_id": None}, "issue", "scope_mismatch", 3),
            (RUNS_PATH, [run_row(issue_id=OTHER)], "runs", "scope_mismatch", 4),
            (RUNS_PATH, [run_row(workspace_id=OTHER)], "runs", "scope_mismatch", 4),
            (RUNS_PATH, [run_row(project_id=OTHER)], "runs", "scope_mismatch", 4),
            (RUNS_PATH, [run_row(restricted=True)], "runs", "restricted_run", 4),
        ]
        for path, body, check, code, count in cases:
            with self.subTest(path=path, code=code, body=body):
                with fixture({**replies(), path: (200, body)}) as (origin, requests):
                    report = client(origin).check_contract(ISSUE, RUN)
                failure = next(row for row in report["checks"] if row["status"] == "fail")
                self.assertEqual((failure["check"], failure["code"]), (check, code))
                self.assertEqual(len(requests), count)

    def test_reports_required_field_or_envelope_drift_without_echoing_values(self):
        missing_project = {key: value for key, value in replies()[ISSUE_PATH][1].items() if key != "project_id"}
        missing_timestamp = {key: value for key, value in run_row().items() if key != "completed_at"}
        cases = [
            (ME_PATH, {"user": {"id": USER}}, "schema_drift", "id"),
            (ISSUE_PATH, missing_project, "schema_drift", "project_id"),
            (RUNS_PATH, {"runs": [run_row()]}, "schema_drift", None),
            (RUNS_PATH, [run_row(status={"value": SECRET})], "schema_drift", "status"),
            (RUNS_PATH, [missing_timestamp], "schema_drift", "completed_at"),
            (RUNS_PATH, [run_row(completed_at=SECRET)], "schema_drift", "completed_at"),
            (RUNS_PATH, [run_row(restricted="false")], "schema_drift", "restricted"),
            (RUNS_PATH, b"not JSON; synthetic-private-response-body", "invalid_json", None),
        ]
        for path, payload, code, field in cases:
            with self.subTest(path=path, code=code, field=field):
                with fixture({**replies(), path: (200, payload)}) as (origin, _):
                    report = client(origin).check_contract(ISSUE, RUN)
                failure = next(row for row in report["checks"] if row["status"] == "fail")
                self.assertEqual((failure["code"], failure.get("field")), (code, field))
                self.assertNotIn(SECRET, json.dumps(report))
                self.assertNotIn(TOKEN, json.dumps(report))

    def test_requires_a_unique_exact_run_and_does_not_substitute_the_newest(self):
        for rows, code in [([], "run_not_found"), ([run_row(OTHER_RUN)], "run_not_found"),
                           ([run_row(), run_row()], "duplicate_run")]:
            with self.subTest(code=code, count=len(rows)):
                with fixture({**replies(), RUNS_PATH: (200, rows)}) as (origin, _):
                    with self.assertRaises(MulticaAPIError) as caught:
                        client(origin).get_run(ISSUE, RUN)
                self.assertEqual(caught.exception.code, code)

    def test_rejects_redirects_without_connecting_to_the_destination(self):
        with fixture(replies()) as (destination, destination_requests):
            with fixture({ME_PATH: (302, destination + ME_PATH)}) as (source, source_requests):
                report = client(source).check_contract(ISSUE, RUN)
        self.assertEqual(report["checks"][0]["code"], "redirect_refused")
        self.assertEqual(report["checks"][0]["http_status"], 302)
        self.assertEqual(len(source_requests), 1)
        self.assertFalse(destination_requests)
        self.assertNotIn(destination, json.dumps(report))

    def test_distinguishes_http_auth_visibility_and_availability_errors(self):
        for status, code in [(401, "unauthenticated"), (403, "forbidden"), (404, "not_found_or_hidden"),
                             (429, "rate_limited"), (502, "http_error")]:
            with self.subTest(status=status):
                with fixture({ME_PATH: (status, {"error": SECRET})}) as (origin, _):
                    report = client(origin).check_contract(ISSUE, RUN)
                self.assertEqual((report["checks"][0]["code"], report["checks"][0]["http_status"]), (code, status))
                self.assertNotIn(SECRET, json.dumps(report))

    def test_rejects_untrusted_origin_formats_and_routes_before_network_io(self):
        for origin in ["http://example.test", "https://u:p@example.test", "https://example.test/path",
                       "https://example.test?", "https://example.test#", "https://[::1]extra"]:
            with self.subTest(origin=origin), self.assertRaises(MulticaAPIError):
                client(origin)
        with fixture(replies()) as (origin, requests):
            for issue, run in [("../api/me", RUN), (ISSUE, RUN[:8])]:
                with self.assertRaises(MulticaAPIError):
                    client(origin).get_run(issue, run)
            with self.assertRaises(MulticaAPIError):
                client(origin, token="invalid\r\nheader")
            self.assertFalse(requests)

    def test_private_http_requires_explicit_opt_in_and_dials_the_literal_address(self):
        private_host = "10.42.0.12"
        with self.assertRaises(MulticaAPIError):
            client(f"http://{private_host}:8080")
        for host in ("8.8.8.8", "169.254.169.254", "100.64.0.1", "internal.example", "localhost"):
            with self.subTest(host=host), self.assertRaises(MulticaAPIError):
                client(f"http://{host}:8080", allow_private_http=True)

        with fixture(replies()) as (origin, requests):
            fixture_port = int(origin.rsplit(":", 1)[1])
            with mock.patch("multica_backend.multica_api.HTTPConnection",
                            side_effect=lambda host, port, timeout: HTTPConnection("127.0.0.1", fixture_port, timeout=timeout)) as dial:
                report = client(f"http://{private_host}:8080", allow_private_http=True).check_contract(ISSUE, RUN)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(dial.call_args_list, [mock.call(private_host, 8080, timeout=10)] * 4)
            self.assertEqual(len(requests), 4)

    def test_cli_suppresses_values_in_bad_arguments(self):
        result = invoke_cli("--token", TOKEN)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["code"], "invalid_arguments")

    def test_size_limit_fails_without_returning_partial_history(self):
        oversized = b" " * (8 * 1024 * 1024 + 1)
        with fixture({**replies(), RUNS_PATH: (200, oversized)}) as (origin, _):
            report = client(origin).check_contract(ISSUE, RUN)
        self.assertEqual(report["checks"][3]["code"], "response_too_large")
        self.assertEqual(report["checks"][4]["status"], "not_run")

    def test_cli_requires_explicit_live_and_its_own_token(self):
        with fixture(replies()) as (origin, requests):
            for args, token in [(live_args(origin)[1:], TOKEN), (live_args(origin), None)]:
                with self.subTest(token_supplied=token is not None):
                    result = invoke_cli(*args, token=token)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)["status"], "not_run")
            self.assertFalse(requests)

    def test_cli_emits_a_sanitized_report_for_pass_and_fail(self):
        for responses, exit_code, status in [(replies(), 0, "pass"), ({ME_PATH: (401, TOKEN)}, 1, "fail")]:
            with self.subTest(status=status):
                with fixture(responses) as (origin, _):
                    result = invoke_cli(*live_args(origin), "--candidate-version", "v0.11.0", token=TOKEN)
                report = json.loads(result.stdout)
                self.assertEqual((result.returncode, report["status"]), (exit_code, status))
                self.assertEqual(report["contract_baseline"], "v0.11.0")
                self.assertEqual(report["candidate_version"], "v0.11.0")
                for private in (TOKEN, SECRET, origin, USER, WORKSPACE, PROJECT, ISSUE, RUN):
                    self.assertNotIn(private, result.stdout + result.stderr)
                if status == "pass":
                    self.assertEqual([check["status"] for check in report["checks"]], ["pass"] * 5)
                else:
                    self.assertEqual([check["status"] for check in report["checks"]], ["fail"] + ["not_run"] * 4)


if __name__ == "__main__":
    unittest.main()
