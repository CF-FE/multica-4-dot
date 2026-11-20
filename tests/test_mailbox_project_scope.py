"""Verify the Unix endpoint against a synthetic native Multica API."""

from contextlib import closing
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp"))
spec = importlib.util.spec_from_file_location(
    "mailbox_project_scope", ROOT / "deployment" / "multica-backend" / "project-scope.py",
)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)

USER = "00000000-0000-4000-8000-000000000001"
PROJECT = "00000000-0000-4000-8000-000000000002"
NEW_PROJECT = "aaaaaaaa-0000-4000-8000-000000000003"
OTHER_PROJECT = "00000000-0000-4000-8000-000000000004"
OTHER_WORKSPACE = "00000000-0000-4000-8000-000000000005"
MISSING_PROJECT = "00000000-0000-4000-8000-000000000006"
PROJECT_PREFIX = "/api/projects/"


class NativeFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        server = self.server
        server.reads.append((self.path, self.headers.get("X-Workspace-ID")))
        if self.headers.get("Authorization") != "Bearer fixture":
            self.send_response(401)
            body = {}
        elif self.path == "/api/me":
            self.send_response(200)
            body = {"id": server.user_id}
        else:
            project = self.path.removeprefix(PROJECT_PREFIX)
            workspace = server.projects.get(project)
            self.send_response(200 if workspace else 404)
            body = {"id": project, "workspace_id": workspace, "details": "fixture data"}
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *_args):
        pass


class ProjectScopeTest(unittest.TestCase):
    def setUp(self):
        native = ThreadingHTTPServer(("127.0.0.1", 0), NativeFixture)
        native.user_id = USER
        native.projects = {PROJECT: scope.WORKSPACE_ID, OTHER_PROJECT: OTHER_WORKSPACE}
        native.reads = []
        self.native = native
        worker = Thread(target=native.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        worker.start()
        self.addCleanup(native.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(native.shutdown)

        credentials = TemporaryDirectory()
        self.addCleanup(credentials.cleanup)
        directory = Path(credentials.name)
        (directory / "config.json").write_text(json.dumps({"instances": {"tencent": {
            "origin": f"http://127.0.0.1:{native.server_port}", "expected_user_id": USER,
            "pat_credential": "multica-pat", "workspaces": {scope.WORKSPACE_ID: {}},
        }}}))
        (directory / "multica-pat").write_text("fixture")
        self.lookup = scope.configured_project(directory)

    def request(self, path, method="GET", headers=None):
        peer, server = socket.socketpair()
        with peer, server, closing(HTTPConnection("localhost", timeout=2)) as client:
            peer.settimeout(2)
            server.settimeout(2)
            client.sock = peer
            worker = Thread(target=scope.ProjectScopeHandler, args=(server, self.lookup), daemon=True)
            worker.start()
            client.request(method, path, headers=headers or {})
            with client.getresponse() as response:
                result = response.status, json.loads(response.read())
            worker.join(5)
            self.assertFalse(worker.is_alive())
            return result

    def test_current_and_future_projects_use_native_membership(self):
        self.assertEqual(self.request(PROJECT_PREFIX + PROJECT),
                         (200, {"id": PROJECT, "workspace_id": scope.WORKSPACE_ID}))
        self.assertEqual(self.request(PROJECT_PREFIX + NEW_PROJECT), (404, {}))
        self.native.projects[NEW_PROJECT] = scope.WORKSPACE_ID
        self.assertEqual(self.request(PROJECT_PREFIX + NEW_PROJECT), (
            200, {"id": NEW_PROJECT, "workspace_id": scope.WORKSPACE_ID},
        ))
        self.assertEqual(self.native.reads[-2:], [("/api/me", None),
                                                (PROJECT_PREFIX + NEW_PROJECT, scope.WORKSPACE_ID)])

    def test_other_workspace_and_missing_project_are_indistinguishable(self):
        self.assertEqual(self.request(PROJECT_PREFIX + MISSING_PROJECT), (404, {}))
        self.assertEqual(self.request(PROJECT_PREFIX + OTHER_PROJECT, headers={
            "X-Workspace-ID": OTHER_WORKSPACE, "Authorization": "Bearer untrusted",
        }), (404, {}))
        self.assertEqual(self.native.reads[-1], (PROJECT_PREFIX + OTHER_PROJECT, scope.WORKSPACE_ID))

    def test_invalid_paths_and_methods_do_not_reach_native(self):
        project = PROJECT_PREFIX + PROJECT
        for path in (PROJECT_PREFIX, project + "?scope=all", "/" + project, project + "/issues",
                     PROJECT_PREFIX + NEW_PROJECT.upper(), "http://localhost" + project):
            with self.subTest(path=path):
                self.assertEqual(self.request(path), (404, {}))
        for method in ("POST", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(self.request(project, method), (501, {}))
        self.assertEqual(self.request(project, headers={"Content-Length": "1"}), (400, {}))
        self.assertEqual(self.native.reads, [])

    def test_invalid_identity_blocks_project_lookup(self):
        self.native.user_id = OTHER_WORKSPACE
        self.assertEqual(self.request(PROJECT_PREFIX + PROJECT), (503, {}))
        self.assertEqual(self.native.reads, [("/api/me", None)])
