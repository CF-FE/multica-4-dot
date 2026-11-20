"""Verify a project's native workspace through a systemd-accepted Unix stream."""

from functools import partial
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import socket
import sys

from multica_backend.multica_api import MulticaAPI, MulticaAPIError


WORKSPACE_ID = "e25be43b-82b6-419d-9085-bb5c5700b1af"
PROJECT_PATH = re.compile(r"/api/projects/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})")


class ProjectScopeHandler(BaseHTTPRequestHandler):
    def __init__(self, request, lookup):
        self.lookup = lookup
        super().__init__(request, (), None)

    def log_message(self, *_args):
        pass

    def reply(self, status, result=None):
        body = json.dumps(result or {}, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        self.reply(code)

    def do_GET(self):
        request_line = self.requestline.split()
        path = PROJECT_PATH.fullmatch(request_line[1]) if len(request_line) == 3 else None
        if not path:
            self.reply(404)
            return
        if ("Transfer-Encoding" in self.headers
                or self.headers.get_all("Content-Length", []) not in ([], ["0"])):
            self.reply(400)
            return
        try:
            project = self.lookup(path[1])
        except MulticaAPIError as exc:
            if exc.check == "project" and exc.code in {"scope_mismatch", "not_found_or_hidden", "forbidden"}:
                self.reply(404)
            else:
                self.reply(503)
            return
        self.reply(200, {"id": project.id, "workspace_id": project.workspace_id})


def configured_project(credential_directory):
    instance = json.loads((credential_directory / "config.json").read_text())["instances"]["tencent"]
    if instance["pat_credential"] != "multica-pat" or WORKSPACE_ID not in instance["workspaces"]:
        raise ValueError("invalid project scope configuration")
    token = (credential_directory / "multica-pat").read_text().strip()
    read = partial(MulticaAPI, origin=instance["origin"], token=token,
                   expected_user_id=instance["expected_user_id"], workspace_id=WORKSPACE_ID,
                   allow_private_http=instance.get("allow_private_http", False))
    return lambda project_id: read(project_id=project_id).get_project()


def main():
    try:
        lookup = configured_project(Path(os.environ["CREDENTIALS_DIRECTORY"]))
    except (KeyError, TypeError, ValueError, OSError):
        print("Multica project scope credentials are unavailable or invalid", file=sys.stderr)
        return 1
    with socket.socket(fileno=0) as client:
        if client.family != socket.AF_UNIX or client.type != socket.SOCK_STREAM:
            print("Expected an accepted Unix stream", file=sys.stderr)
            return 1
        client.settimeout(3)
        try:
            ProjectScopeHandler(client, lookup)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
