"""End-to-end fixture with a real TLS receiver and fresh reporter processes."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = Path(__file__).resolve().parents[1] / "reporter" / "run_reporter.py"
WS, PROJECT, ISSUE, RUN, OTHER = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 6)]


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        f = self.server.fixture
        f.requests.append(("GET", self.path))
        if self.path.startswith("/api/issues/"):
            if (self.headers.get("Authorization") != "Bearer fixture-reader" or
                    self.headers.get("X-Workspace-ID") != WS):
                return self.respond(403, {})
            if self.path == "/api/issues/" + ISSUE:
                return self.respond(f.issue_code, f.issue)
            if self.path == f"/api/issues/{ISSUE}/task-runs?scope=issue&view=timeline":
                return self.respond(200, f.runs)
        if self.path.startswith("/mailbox/api/v1/observations/batches/"):
            if self.headers.get("Authorization") != "Bearer fixture-source":
                return self.respond(401, {})
            batch_id = self.path.rsplit("/", 1)[1]
            if f.lookup_error:
                return self.respond(*f.lookup_error)
            if batch_id in f.saved and not f.hide_receipt:
                return self.respond(200, f.saved[batch_id][1])
            return self.respond(404, {"error": {"code": "NOT_FOUND", "message": "Observation receipt not found",
                                                "retryable": False}, "request_id": "fixture-request"})
        self.respond(404, {})

    def do_POST(self):
        f = self.server.fixture
        f.requests.append(("POST", self.path))
        if (self.path != "/mailbox/api/v1/observations/batches" or
                self.headers.get("Authorization") != "Bearer fixture-source"):
            return self.respond(403, {})
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        f.posts.append(raw)
        batch = json.loads(raw)
        eid = batch["events"][0]["event_id"]
        bid = batch["batch_id"]
        if f.post_conflict or (bid in f.saved and raw != f.saved[bid][0]):
            return self.respond(409, {"error": {"code": "OBSERVATION_CONFLICT"}})
        receipt = {"source_id": batch["source_id"], "batch_id": bid, "persisted": True,
                   "accepted_event_ids": [eid], "duplicate_event_ids": [], "watermark": "1"}
        f.saved.setdefault(bid, (raw, receipt))
        if f.lose_reply:
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.respond(200, receipt)


class RunReporterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.cert = root / "localhost.crt"
        key = root / "localhost.key"
        cfg = root / "openssl.cnf"
        cfg.write_text("[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n"
                       "[dn]\nCN=localhost\n[ext]\nsubjectAltName=IP:127.0.0.1\nbasicConstraints=CA:TRUE\n")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-config", str(cfg), "-keyout", str(key), "-out", str(cls.cert)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, key)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.server.fixture = self
        self.origin = "https://127.0.0.1:" + str(self.server.server_port)
        self.watch = {"issue_id": ISSUE, "run_id": RUN, "task_id": "pilot.task", "job_id": "pilot.job"}
        self.settings = {"multica_origin": self.origin, "mailbox_api": self.origin + "/mailbox/api/v1",
                         "workspace_id": WS, "project_id": PROJECT, "mailbox_project_id": "pilot",
                         "source_id": "pilot-source", "watches": [self.watch]}
        (self.root / "multica.token").write_text("fixture-reader\n")
        (self.root / "mailbox.token").write_text("fixture-source\n")
        self.issue = {"id": ISSUE, "workspace_id": WS, "project_id": PROJECT}
        self.run = {"id": RUN, "issue_id": ISSUE, "workspace_id": WS, "status": "failed",
                    "completed_at": "2026-11-20T01:02:03.123456Z", "error": "PRIVATE ERROR CONTENT"}
        self.runs = [self.run]
        self.saved = {}
        self.requests = []
        self.posts = []
        self.issue_code = 200
        self.lookup_error = None
        self.lose_reply = self.hide_receipt = self.post_conflict = False

    def poll(self, ok):
        (self.root / "config.json").write_text(json.dumps(self.settings))
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--config", str(self.root / "config.json"),
                                 "--database", str(self.root / "state.sqlite3")],
                                env={**os.environ, "CREDENTIALS_DIRECTORY": str(self.root),
                                     "SSL_CERT_FILE": str(self.cert)}, capture_output=True, text=True)
        output = result.stdout + result.stderr
        self.assertNotIn("PRIVATE ERROR CONTENT", output)
        self.assertNotIn("fixture-source", output)
        self.assertEqual(result.returncode == 0, ok, output)
        return output

    def test_lost_reply_reopens_database_and_confirms_without_reposting_or_rereading_run(self):
        self.lose_reply = True
        self.poll(False)
        self.assertEqual(len(self.saved), 1)
        body = self.posts[0]
        self.assertNotIn(b"PRIVATE ERROR CONTENT", body)
        event, = json.loads(body)["events"]
        self.assertEqual((event["run_id"], event["task_id"], event["project_id"]), (RUN, "pilot.task", "pilot"))
        self.assertEqual(event["occurred_at"], self.run["completed_at"])
        self.assertIn("failed", event["payload"]["reported_status"])
        self.assertEqual(event["event_type"], "activity")
        self.assertTrue(any(e["authority"] == "native_observation" and RUN in e["ref"] for e in event["evidence"]))
        self.assertIn(b"pilot.job", body)
        self.issue_code = 503
        self.requests.clear()
        self.poll(True)
        self.assertEqual(self.requests, [("GET", "/mailbox/api/v1/observations/batches/" + next(iter(self.saved)))])
        self.requests.clear()
        self.poll(True)
        self.assertEqual(self.requests, [])

    def test_duplicate_delivery_uses_frozen_bytes(self):
        self.lose_reply = True
        self.run.pop("error")
        self.run["has_error"] = True
        self.poll(False)
        event, = json.loads(self.posts[0])["events"]
        self.assertTrue(any(item["source_type"] == "multica_run_error" for item in event["evidence"]))
        self.assertEqual(len(self.posts), 1)
        self.hide_receipt, self.lose_reply = True, False
        self.run.update(status="completed", completed_at=None)
        self.poll(True)
        self.assertEqual(self.posts, [self.posts[0]] * 2)
        self.assertEqual(len(self.saved), 1)

    def test_proxy_404_and_storage_outage_keep_record_until_recovery(self):
        for error in [(404, {"detail": "Not Found"}), (503, {}), (403, {}), (200, None)]:
            self.lookup_error = error
            self.poll(False)
            self.assertFalse(self.posts)
        self.lookup_error = None
        self.issue_code = 503
        self.poll(True)
        self.assertEqual(len(self.saved), 1)

    def test_scope_mismatch_missing_run_or_unavailable_source_never_posts(self):
        for obj, key in [(self.issue, "id"), (self.issue, "workspace_id"), (self.issue, "project_id"),
                         (self.run, "id"), (self.run, "workspace_id"), (self.run, "issue_id")]:
            with self.subTest(key=key):
                previous = obj[key]
                obj[key] = OTHER
                self.poll(False)
                obj[key] = previous
        self.run["restricted"] = True
        self.poll(False)
        del self.run["restricted"]
        self.issue_code = 503
        self.poll(False)
        self.assertFalse(self.posts)
        self.assertFalse(any("/mailbox/" in p for _, p in self.requests))

    def test_only_exact_registered_terminal_run_is_recorded(self):
        self.run.update(status="running", completed_at=None)
        self.runs.insert(0, {**self.run, "id": OTHER, "status": "failed"})
        self.poll(True)
        self.assertFalse(self.posts)
        self.run["status"] = "cancelled"
        self.poll(True)
        event, = json.loads(self.posts[0])["events"]
        self.assertIn("cancelled", event["payload"]["reported_status"])
        self.assertIsNone(event["occurred_at"])

        self.settings["watches"] = [{"issue_id": ISSUE, "run_id": OTHER, "task_id": "other-task"}]
        self.runs[0]["status"] = "completed"
        self.poll(True)
        event, = json.loads(self.posts[-1])["events"]
        self.assertEqual(event["payload"], {"reported_status": "Multica Run completed"})
        self.assertFalse(any(e["source_type"] == "registered_mailbox_job" for e in event["evidence"]))

    def test_conflict_is_quarantined_across_restart(self):
        self.post_conflict = True
        self.poll(False)
        self.assertEqual(len(self.posts), 1)
        self.requests.clear()
        self.poll(False)
        self.assertEqual(self.requests, [])

    def test_invalid_receipt_retains_observation(self):
        self.lose_reply = True
        self.poll(False)
        _, original = next(iter(self.saved.values()))
        for changes in [{"source_id": "other"}, {"batch_id": "other"}, {"persisted": 1},
                        {"watermark": "invalid"}, {"accepted_event_ids": ["other"]},
                        {"duplicate_event_ids": original["accepted_event_ids"]}]:
            self.lookup_error = (200, {**original, **changes})
            self.poll(False)
        self.lookup_error = None
        self.poll(True)
        self.assertEqual(len(self.posts), 1)

    def test_ephemeral_multica_run_token_is_rejected_before_network(self):
        (self.root / "multica.token").write_text("mat_fixture")
        self.poll(False)
        self.assertEqual(self.requests, [])

    def test_ledger_contains_frozen_body_and_precise_duplicate_receipt(self):
        self.lose_reply = True
        self.poll(False)
        batch_id, (raw, receipt) = next(iter(self.saved.items()))
        duplicate = {**receipt, "duplicate_event_ids": receipt["accepted_event_ids"], "accepted_event_ids": []}
        self.lookup_error = (200, duplicate)
        self.poll(True)
        with sqlite3.connect(self.root / "state.sqlite3") as db:
            body, confirmation = db.execute("SELECT original, receipt FROM outbox WHERE run_id=?", (RUN,)).fetchone()
        self.assertEqual(body, raw)
        self.assertEqual(json.loads(body)["batch_id"], batch_id)
        self.assertEqual(json.loads(confirmation), duplicate)

    def test_new_origin_or_project_cannot_redirect_pending_batch(self):
        self.lookup_error = (503, {})
        self.poll(False)
        self.requests.clear()
        self.settings["mailbox_project_id"] = "other"
        self.poll(False)
        self.assertEqual(self.requests, [])

    def test_removed_or_remapped_registration_does_not_forward_pending_content(self):
        self.lookup_error = (503, {})
        self.poll(False)
        self.lookup_error = None
        self.settings["watches"] = []
        self.poll(True)
        self.settings["watches"] = [{**self.watch, "task_id": "other-task"}]
        self.poll(False)
        self.assertFalse(self.posts)
        self.settings["watches"] = [self.watch]
        self.poll(True)
        self.assertEqual(len(self.posts), 1)


if __name__ == "__main__":
    unittest.main()
