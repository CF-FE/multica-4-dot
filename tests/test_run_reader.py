import hashlib
from http.client import HTTPConnection
from pathlib import Path
import sys
from threading import Thread
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deployment" / "run-reader"))
from run_reader import Reader, HTTPServer

ISSUE = "00000000-0000-4000-8000-000000000003"
WORKSPACE = "00000000-0000-4000-8000-000000000001"
ISSUE_PATH = f"/api/issues/{ISSUE}"
RUNS_PATH = ISSUE_PATH + "/task-runs?scope=issue&view=timeline"
HEADERS = {"Authorization": "Bearer fixture", "X-Workspace-ID": WORKSPACE}


class RunReaderTest(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), Reader)
        self.server.token_digest = hashlib.sha256(b"Bearer fixture").digest()
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, path, *, method="GET", headers=HEADERS):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()

    def test_exact_read_routes_reach_their_projection(self):
        with patch("run_reader.query", return_value='{"id":"fixture"}') as lookup:
            self.assertEqual(self.request(ISSUE_PATH), (200, b'{"id":"fixture"}'))
            lookup.assert_called_once_with(ISSUE, WORKSPACE, False)
        with patch("run_reader.query", return_value='[]') as lookup:
            self.assertEqual(self.request(RUNS_PATH), (200, b'[]'))
            lookup.assert_called_once_with(ISSUE, WORKSPACE, True)

    def test_bad_bearer_routes_and_methods_fail_before_database(self):
        with patch("run_reader.query") as lookup:
            self.assertEqual(self.request(ISSUE_PATH, headers={})[0], 401)
            self.assertEqual(self.request(ISSUE_PATH, headers={**HEADERS, "Authorization": "Bearer wrong"})[0], 401)
            self.assertEqual(self.request(ISSUE_PATH, headers={**HEADERS, "X-Workspace-ID": "bad"})[0], 400)
            for route in ["/api/issues", ISSUE_PATH + "/comments", ISSUE_PATH + "?fields=title", RUNS_PATH + "&scope=subtree"]:
                self.assertEqual(self.request(route)[0], 404)
            for method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]:
                self.assertEqual(self.request(ISSUE_PATH, method=method)[0], 405)
            lookup.assert_not_called()

    def test_database_error_and_absent_registration_are_distinct(self):
        with patch("run_reader.query", return_value=""):
            self.assertEqual(self.request(RUNS_PATH)[0], 404)
        with patch("run_reader.query", side_effect=OSError("private diagnostic")):
            status, body = self.request(ISSUE_PATH)
            self.assertEqual(status, 503)
            self.assertNotIn(b"private diagnostic", body)


if __name__ == "__main__":
    unittest.main()
