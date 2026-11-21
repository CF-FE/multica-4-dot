"""Exercise the operator entry point across process restarts and a real loopback connection."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


@unittest.skipIf(os.name == "nt", "this CLI-profile fixture uses a POSIX executable")
class WireRecoveryTest(unittest.TestCase):
    def test_dropped_post_then_fresh_process_recovers_only_the_registered_wakeup(self):
        root = Path(__file__).resolve().parents[1]
        example = json.loads((root / "docs/unblock-record-format.md").read_text()
                             .split("```json\n", 1)[1].split("\n```", 1)[0])
        reg, snap = example["registration"], example["snapshot"]
        now = datetime.now(timezone.utc)
        observed = now - timedelta(minutes=4)
        for role in reg["roles"].values():
            role.update(valid_from=(now - timedelta(days=1)).isoformat(), valid_until=None)
        snap.update(recorded_at=observed.isoformat(), due_at=(now - timedelta(minutes=2)).isoformat(),
                    decision_due_at=None, evidence={})
        if "pickup" in snap:
            snap["pickup"]["at"] = (observed - timedelta(minutes=1)).isoformat()
        subject, rule, run = (str(uuid4()) for _ in range(3))
        issue_path = "/api/issues/" + reg["issue_id"]
        wakeups = issue_path + "/wakeups"
        scope = {k: reg[k] for k in ("issue_id", "workspace_id", "project_id")}
        post_bodies, reminders, runs = [], [], []
        active_status = "blocked"
        routes = {
            "/api/me": {"id": subject},
            "/api/projects/" + reg["project_id"]: {"id": reg["project_id"], "workspace_id": reg["workspace_id"]},
            issue_path: {**scope, "id": reg["issue_id"], "status": active_status},
            "/api/agents/" + reg["coordinator_id"]: {"id": reg["coordinator_id"],
                "workspace_id": reg["workspace_id"], "system_key": "mika", "archived_at": None},
            "/api/issue-statuses": {"statuses": [{"workspace_id": reg["workspace_id"],
                                                  "key": active_status, "category": "blocked"}]},
            issue_path + "/comments?thread=" + reg["thread_id"]: [{
                "id": reg["thread_id"], "type": "comment", "parent_id": None, "issue_id": reg["issue_id"],
                "author_type": "agent", "author_id": reg["coordinator_id"],
                "created_at": observed.isoformat(), "updated_at": observed.isoformat(),
                "content": "/note unblock.v1 " + json.dumps(snap),
            }],
            issue_path + "/task-runs?scope=issue&view=timeline": runs,
            wakeups: reminders, wakeups + "/" + rule + "/runs": runs,
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path not in routes or self.headers.get("Authorization") != "Bearer mul_test_only":
                    self.send_error(404)
                    return
                data = json.dumps(routes[self.path]).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path != wakeups or self.headers.get("Authorization") != "Bearer mul_test_only":
                    self.send_error(404)
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                post_bodies.append(body)
                reminders.append({**scope, **body, "id": rule, "created_by": subject, "revision": 1,
                                  "created_by_agent": False, "source_task_id": None, "enabled": True,
                                  "event_types": ["issue.status_changed"], "expiry_seconds": 60,
                                  "created_at": now.isoformat(), "expires_at": (now + timedelta(seconds=60)).isoformat()})
                self.close_connection = True  # Native side persisted the rule; the HTTP reply is lost.

        with tempfile.TemporaryDirectory() as tmp, ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            http = threading.Thread(target=server.serve_forever, daemon=True)
            http.start()
            try:
                work = Path(tmp)
                origin = f"http://127.0.0.1:{server.server_port}"
                binary = work / "multica-profile-fixture"
                binary.write_text("#!/bin/sh\ncase \"$3\" in\n"
                                  f"  config) printf 'Profile: fixture\\nserver_url: {origin}\\n' ;;\n"
                                  "  *) exit 2 ;;\nesac\n")
                binary.chmod(0o700)
                reg.update(cli_path=str(binary), cli_profile="fixture", expected_user_id=subject,
                           origin=origin, notifications_enabled=True)
                case_fields = ("issue_id", "thread_id")
                catalog = {"projects": [{"defaults": {k: v for k, v in reg.items() if k not in case_fields},
                                         "cases": [{k: reg[k] for k in case_fields}]}]}
                config = work / "cases.json"
                config.write_text(json.dumps(catalog))
                db = work / "checkpoint.sqlite"

                def cli(command, *flags):
                    invocation = subprocess.run(
                        [sys.executable, "-B", "-m", "unblock", command, "--config", str(config), *flags],
                        cwd=root, env={**os.environ, "MULTICA_UNBLOCK_ACCESS_TOKEN": "mul_test_only"},
                        capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(invocation.returncode, 0, invocation.stdout + invocation.stderr)
                    return json.loads(invocation.stdout)["cases"][0]

                self.assertTrue(cli("g8")["assessment"]["g8_pending"])
                self.assertEqual(cli("tick")["notification"], "preview")
                self.assertEqual(post_bodies, [])
                first = cli("tick", "--db", str(db), "--apply")["notification"]
                self.assertEqual(first["status"], "unknown")
                self.assertEqual(len(post_bodies), 1)
                self.assertEqual(post_bodies[0]["agent_id"], reg["coordinator_id"])
                self.assertEqual(post_bodies[0]["parent_comment_id"], reg["thread_id"])
                runs.append({**scope, "id": run, "agent_id": reg["coordinator_id"], "status": "running",
                             "created_at": now.isoformat(), "started_at": now.isoformat()})
                reminders[0].update(enabled=False, last_task_id=run)
                recovered = cli("recover", "--db", str(db), "--issue", reg["issue_id"],
                                "--checkpoint", snap["checkpoint_id"])["notification"]
                self.assertEqual(recovered["status"], "confirmed")
                self.assertEqual(recovered["receipt"]["run_id"], run)
                self.assertEqual(recovered["marker"], first["marker"])
                self.assertEqual(cli("tick", "--db", str(db), "--apply")["notification"], recovered)
                self.assertEqual(len(post_bodies), 1)
            finally:
                server.shutdown()
                http.join(timeout=5)
