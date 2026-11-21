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

try:
    from multica_backend.native_operations import NativeOperations
except ModuleNotFoundError as exc:
    if exc.name != "multica_backend":
        raise
    from mcp.multica_backend.native_operations import NativeOperations

from unblock.native import NativeHTTP


@unittest.skipIf(os.name == "nt", "this CLI-profile fixture uses a POSIX executable")
class WireRecoveryTest(unittest.TestCase):
    def test_waiting_for_pickup_after_original_card_handoff_and_wakeup_replay(self):
        root = Path(__file__).resolve().parents[1]
        example = json.loads((root / "docs/unblock-record-format.md").read_text()
                             .split("```json\n", 1)[1].split("\n```", 1)[0])
        reg, snap = example["registration"], example["snapshot"]
        now = datetime.now(timezone.utc)
        observed = now - timedelta(minutes=4)
        for role in reg["roles"].values():
            role.update(valid_from=(now - timedelta(days=1)).isoformat(), valid_until=None)
        snap.update(recorded_at=observed.isoformat(), due_at=None, decision_due_at=None, evidence={},
                    mailbox_result_version=0)
        snap.pop("pickup", None)
        subject, rule, run, handoff_member, handoff_id = (str(uuid4()) for _ in range(5))
        issue_path = "/api/issues/" + reg["issue_id"]
        wakeups = issue_path + "/wakeups"
        notes = issue_path + "/comments"
        scope = {k: reg[k] for k in ("issue_id", "workspace_id", "project_id")}
        post_bodies, reminders, runs, original_notes = [], [], [], []
        handoff_at = (observed + timedelta(minutes=1)).isoformat()
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
            issue_path + "/comments?roots_only=true": original_notes,
            issue_path + "/task-runs?scope=issue&view=timeline": runs,
            wakeups: reminders, wakeups + "/" + rule + "/runs": runs,
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply_json(self, status, payload):
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                auth = self.headers.get("Authorization")
                if self.path not in routes or auth not in ("Bearer mul_test_only", "Bearer mul_handoff_test_only"):
                    self.send_error(404)
                    return
                if self.path == "/api/me" and auth == "Bearer mul_handoff_test_only":
                    self.reply_json(200, {"id": handoff_member})
                else:
                    self.reply_json(200, routes[self.path])

            def do_POST(self):
                if self.path == notes and self.headers.get("Authorization") == "Bearer mul_handoff_test_only":
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    row = {
                        "id": handoff_id, "type": "comment", "parent_id": None, "issue_id": reg["issue_id"],
                        "author_type": "member", "author_id": handoff_member,
                        "created_at": handoff_at, "updated_at": handoff_at, "content": body["content"],
                    }
                    original_notes.append(row)
                    self.reply_json(201, row)
                    return
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
                           origin=origin, notifications_enabled=True, handoff_member_id=handoff_member)
                case_fields = ("issue_id", "thread_id")
                catalog = {"projects": [{"defaults": {k: v for k, v in reg.items() if k not in case_fields},
                                         "cases": [{k: reg[k] for k in case_fields}]}]}
                config = work / "cases.json"
                config.write_text(json.dumps(catalog))
                db = work / "checkpoint.sqlite"

                def cli(command, *flags, expected_exit=0, expect_case=True):
                    env = {**os.environ, "MULTICA_UNBLOCK_ACCESS_TOKEN": "mul_test_only"}
                    env.pop("MULTICA_BACKEND_MAILBOX_URL", None)
                    invocation = subprocess.run(
                        [sys.executable, "-B", "-m", "unblock", command, "--config", str(config), *flags],
                        cwd=root, env=env,
                        capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(invocation.returncode, expected_exit, invocation.stdout + invocation.stderr)
                    report = json.loads(invocation.stdout)
                    self.assertEqual(report["source_reads_complete"], expected_exit == 0)
                    self.assertEqual(len(report["cases"]), int(expect_case))
                    return report["cases"][0] if expect_case else report

                idle = cli("g8")
                self.assertEqual(idle["assessment"]["state"], "awaiting_pickup")
                self.assertEqual(idle["notification"], "quiet")
                self.assertEqual(idle["hints"], [])
                self.assertFalse(db.exists())

                issue = routes[issue_path]
                issue["status"] = "done"
                self.assertEqual(cli("g8", expect_case=False)["cases"], [])
                issue["status"] = "unrecognized_status"
                unknown_status = cli("g8", expected_exit=1)
                self.assertIsNone(unknown_status["issue_closed"])
                self.assertIn("issue_status_unconfirmed", unknown_status["pending"])
                self.assertEqual(unknown_status["notification"], "source_unconfirmed")
                issue["status"] = active_status

                registration = catalog["projects"][0]["cases"][0]
                registration["mailbox"] = {"job_id": "fixture-job", "payload_hash": "a" * 64,
                                           "recipient": "fixture-recipient"}
                config.write_text(json.dumps(catalog))
                incomplete = cli("g8", expected_exit=1)
                self.assertEqual(incomplete["assessment"]["state"], "awaiting_pickup")
                self.assertEqual(incomplete["pending"], ["mailbox:not_configured"])
                self.assertEqual(incomplete["notification"], "source_unconfirmed")
                self.assertEqual(post_bodies, [])
                self.assertFalse(db.exists())
                del registration["mailbox"]
                config.write_text(json.dumps(catalog))

                # G8 uses a stable request ID and the native gateway's quiet-note operation.
                handoff = {name: snap[name] for name in ("instance_id", "workspace_id", "project_id",
                           "issue_id", "thread_id", "coordinator_id", "checkpoint_id")}
                handoff["evidence_ref"] = "fixture:bounded-action"
                arguments = {
                    **scope, "request_id": str(uuid4()),
                    "content": "unblock.handoff.v1 " + json.dumps(handoff),
                }
                gateway = NativeOperations(NativeHTTP(origin=origin, token="mul_handoff_test_only"),
                                           instance_id=reg["instance_id"], expected_user_id=handoff_member,
                                           state_path=work / "gateway.sqlite")
                note = gateway.call("fixture-g8", "add_issue_note", arguments)
                self.assertEqual(note["status"], "confirmed")
                self.assertEqual(note["receipt"]["comment_id"], handoff_id)
                self.assertEqual(note["receipt"]["trigger_policy"], "suppressed")
                self.assertEqual(gateway.call("fixture-g8", "add_issue_note", arguments), note)
                self.assertEqual(len(original_notes), 1)
                self.assertEqual(runs, [])

                preview = cli("g8")
                self.assertEqual(preview["assessment"]["state"], "awaiting_pickup")
                self.assertEqual(preview["hints"], [f"patrol_handoff:{handoff_id}"])
                self.assertEqual(cli("tick")["notification"], "preview")
                self.assertEqual(post_bodies, [])
                first = cli("tick", "--db", str(db), "--apply")["notification"]
                self.assertEqual(first["status"], "unknown")
                self.assertEqual(len(post_bodies), 1)
                self.assertEqual(cli("g8")["assessment"]["state"], "awaiting_pickup")
                replay = cli("tick", "--db", str(db), "--apply")["notification"]
                self.assertEqual((replay["status"], replay["marker"]), ("unknown", first["marker"]))
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
                self.assertEqual(cli("g8")["assessment"]["state"], "awaiting_pickup")
                self.assertEqual(cli("tick", "--db", str(db), "--apply")["notification"], recovered)
                self.assertEqual(len(post_bodies), 1)
                self.assertEqual([row["id"] for row in runs], [run])

                signed_at = datetime.now(timezone.utc).isoformat()
                pickup_note_id = str(uuid4())
                pickup_ref = f"multica:comment:{pickup_note_id}"
                verified = {**snap, "revision": 2, "recorded_at": signed_at}
                verified["pickup"] = {
                    "ref": pickup_ref, "actor_id": reg["roles"]["project_lead"]["id"],
                    "at": signed_at, "source_scope": {**scope, "instance_id": reg["instance_id"],
                                                     "thread_id": reg["thread_id"]},
                    "target_id": snap["target"]["id"], "target_version": snap["target"]["version"],
                    "checkpoint_id": snap["checkpoint_id"], "step": snap["target"]["step"],
                }
                thread = routes[issue_path + "/comments?thread=" + reg["thread_id"]]
                thread.append({
                    **thread[0], "id": str(uuid4()), "parent_id": reg["thread_id"],
                    "created_at": signed_at, "updated_at": signed_at,
                    "content": "/note unblock.v1 " + json.dumps(verified),
                })
                alleged = cli("g8", expected_exit=1)
                self.assertEqual(alleged["assessment"]["state"], "awaiting_pickup")
                self.assertIsNone(alleged["assessment"]["pickup_ref"])
                self.assertIn("pickup_source_unconfirmed", alleged["pending"])

                pickup = verified["pickup"]
                receipt = {field: pickup[field] for field in ("checkpoint_id", "step", "target_id", "target_version")}
                receipt["thread_id"] = reg["thread_id"]
                thread.append({
                    **thread[0], "id": pickup_note_id, "parent_id": reg["thread_id"],
                    "author_id": pickup["actor_id"], "author_type": "agent",
                    "created_at": pickup["at"], "updated_at": pickup["at"],
                    "content": "/note unblock.pickup.v1 " + json.dumps(receipt),
                })
                received = cli("summary")["assessment"]
                self.assertEqual(received["state"], "blocked")
                self.assertEqual(received["pickup_ref"], pickup_ref)
                self.assertEqual(len(post_bodies), 1)
            finally:
                server.shutdown()
                http.join(timeout=5)
