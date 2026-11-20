"""Serve the reporter's two Issue reads from the authorized DB projection."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import re
import subprocess
import sys
from uuid import UUID

PATH = re.compile(r"/api/issues/([0-9a-f-]{36})(/task-runs\?scope=issue&view=timeline)?")
ISSUE = """
SELECT row_to_json(i)
FROM run_reporter.issues i
WHERE i.id = :'issue_id'::uuid AND i.workspace_id = :'workspace_id'::uuid;
"""
RUNS = """
SELECT coalesce(
    (SELECT json_agg(r ORDER BY r.id) FROM run_reporter.runs r
     WHERE r.issue_id = i.id AND r.workspace_id = i.workspace_id),
    '[]'::json
)
FROM run_reporter.issues i
WHERE i.id = :'issue_id'::uuid AND i.workspace_id = :'workspace_id'::uuid;
"""


def query(issue_id, workspace_id, runs):
    result = subprocess.run(
        ["psql", "-XqAtw", "-v", "ON_ERROR_STOP=1", "-v", f"issue_id={issue_id}",
         "-v", f"workspace_id={workspace_id}"],
        input=RUNS if runs else ISSUE, capture_output=True, text=True, check=True, timeout=7,
    )
    return result.stdout.strip()


class Reader(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(4)
        super().setup()

    def log_message(self, *_):
        pass

    def reply(self, status, body=b"{}"):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if status == 405:
            self.send_header("Allow", "GET")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        authorization = self.headers.get_all("Authorization", [])
        if len(authorization) != 1 or not hmac.compare_digest(
            hashlib.sha256(authorization[0].encode("latin-1")).digest(), self.server.token_digest
        ):
            self.reply(401)
            return
        match = PATH.fullmatch(self.path)
        if match is None:
            self.reply(404)
            return
        workspace = self.headers.get_all("X-Workspace-ID", [])
        try:
            issue_id = str(UUID(match[1]))
            if len(workspace) != 1:
                raise ValueError
            workspace_id = str(UUID(workspace[0]))
        except ValueError:
            self.reply(400)
            return

        runs = match[2] is not None
        try:
            result = query(issue_id, workspace_id, runs)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"projection read failed ({type(exc).__name__})", file=sys.stderr, flush=True)
            self.reply(503)
            return
        if not result:
            self.reply(404)
            return
        self.reply(200, result.encode("utf-8"))

    def reject_write(self):
        self.reply(405)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = reject_write


if __name__ == "__main__":
    digest = bytes.fromhex(Path("/run/reader/http.sha256").read_text().strip())
    if len(digest) != hashlib.sha256().digest_size:
        sys.exit("invalid HTTP credential digest")
    with HTTPServer(("0.0.0.0", 8080), Reader) as server:
        server.token_digest = digest
        server.serve_forever()
