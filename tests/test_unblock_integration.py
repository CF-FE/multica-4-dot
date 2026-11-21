import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from unblock.__main__ import main, registrations, run_case, scope_key
from unblock.ledger import reconcile_existing


class CheckpointLoopTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "checkpoint.sqlite"
        self.config = Path(tmp.name) / "cases.json"
        guide = Path(__file__).resolve().parents[1] / "docs/unblock-record-format.md"
        example = json.loads(guide.read_text().split("```json\n", 1)[1].split("\n```", 1)[0])
        self.reg = example["registration"]
        self.reg["notifications_enabled"] = True
        self.snapshot = example["snapshot"]
        self.clock = lambda: datetime.fromisoformat(self.snapshot["recorded_at"])
        self.hints = ["original-job:version:3"]
        self.pending = []
        self.sent = []
        self.receipts = {}
        self.disconnect = False

    def poll(self):
        return {"snapshot": copy.deepcopy(self.snapshot), "hints": self.hints, "pending": self.pending}

    def notify(self, marker):
        self.sent.append(marker)
        self.receipts[marker] = {
            "marker": marker, "wakeup_id": "185861dd-ce49-4454-8fe8-20bf4dc27acb",
            "run_id": "24498301-fdea-44a1-a100-73b38ce26aa4", "state": "started",
            "started_at": self.snapshot["recorded_at"],
        }
        if self.disconnect:
            raise TimeoutError
        return self.receipts[marker]

    def check_ready(self):
        return None

    def lookup(self, marker):
        return None if self.disconnect else self.receipts.get(marker)

    def tick(self, apply=False):
        return run_case(self.reg, self, apply=apply, db_path=self.db, clock=self.clock)

    def write_catalog(self):
        local = {"issue_id", "thread_id", "checkpoint_id"}
        defaults = {k: v for k, v in self.reg.items() if k not in local}
        case = {k: v for k, v in self.reg.items() if k in local}
        catalog = {"projects": [{"defaults": defaults, "cases": [case]}]}
        self.config.write_text(json.dumps(catalog))
        return catalog

    def test_preview_pause_and_unavailable_source_have_no_notification_side_effect(self):
        self.assertEqual(self.tick()["notification"], "preview")
        self.assertFalse(self.db.exists())
        self.reg["notifications_enabled"] = False
        self.assertEqual(self.tick(True)["notification"], "disabled")
        self.reg["notifications_enabled"] = True
        self.pending = ["mailbox_unavailable"]
        self.assertEqual(self.tick(True)["notification"], "source_unconfirmed")
        self.assertEqual(self.sent, [])
        self.assertFalse(self.db.exists())

    def test_checkpoint_reconciles_after_lost_reply_even_after_signals_disappear(self):
        self.disconnect = True
        result = self.tick(True)
        self.assertEqual(result["notification"]["status"], "unknown")
        self.hints = []
        self.disconnect = False
        self.reg["notifications_enabled"] = False
        receipt = reconcile_existing(self.db, scope_key(self.reg), self.snapshot["checkpoint_id"], self.lookup)
        self.assertEqual(receipt["status"], "confirmed")
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(receipt["marker"], result["notification"]["marker"])

    def test_arrival_and_deadline_share_one_notification(self):
        first = self.tick(True)
        self.hints = []
        self.clock = lambda: datetime.fromisoformat(self.snapshot["due_at"])
        second = self.tick(True)
        self.assertEqual(first["notification"]["status"], "confirmed")
        self.assertEqual(second["notification"], first["notification"])
        self.assertEqual(len(self.sent), 1)

    def test_changed_revision_or_scope_does_not_consume_an_attempt(self):
        first = self.poll()
        next_read = copy.deepcopy(first)
        next_read["snapshot"]["revision"] += 1
        with patch.object(self, "poll", side_effect=[first, next_read]):
            self.assertEqual(self.tick(True)["notification"], "changed")
        self.assertFalse(self.db.exists())
        self.snapshot["project_id"] = "another-project"
        with self.assertRaises(ValueError):
            self.tick(True)
        self.assertFalse(self.db.exists())

    def test_busy_run_defers_without_burning_checkpoint_then_rechecks(self):
        with patch.object(self, "check_ready", return_value="issue_run_in_flight"):
            row = self.tick(True)
        self.assertEqual(row["hold_reason"], "issue_run_in_flight")
        self.assertFalse(self.db.exists())
        self.assertEqual(self.tick(True)["notification"]["status"], "confirmed")
        self.assertEqual(len(self.sent), 1)

    def test_catalog_cannot_override_project_identity(self):
        catalog = self.write_catalog()
        self.assertEqual(registrations(self.config), [self.reg])
        catalog["projects"][0]["cases"][0]["workspace_id"] = self.reg["workspace_id"]
        self.config.write_text(json.dumps(catalog))
        with self.assertRaises(ValueError):
            registrations(self.config)

    def test_workspace_registry_required_for_production_and_supplies_coordinator(self):
        catalog = self.write_catalog()
        with self.assertRaisesRegex(ValueError, "missing workspace coordinator registry"):
            registrations(self.config, require_workspace_coordinators=True)
        self.assertEqual(registrations(self.config), [self.reg])

        defaults = catalog["projects"][0]["defaults"]
        appointed = defaults.pop("coordinator_id")
        catalog["workspace_coordinators"] = {self.reg["instance_id"]: {
            self.reg["workspace_id"]: appointed,
        }}
        self.config.write_text(json.dumps(catalog))
        self.assertEqual(registrations(self.config, require_workspace_coordinators=True), [self.reg])
        catalog["projects"][0]["cases"][0]["coordinator_id"] = appointed
        self.config.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, "case overlaps project-owned fields"):
            registrations(self.config, require_workspace_coordinators=True)

    def test_legacy_catalog_rejects_conflicting_enabled_projects_in_one_workspace(self):
        catalog = self.write_catalog()
        second = copy.deepcopy(catalog["projects"][0])
        alternate = str(UUID(int=21))
        second["defaults"].update(project_id=str(UUID(int=22)), coordinator_id=alternate)
        second["defaults"]["roles"]["coordinator"]["id"] = alternate
        second["cases"][0].update(issue_id=str(UUID(int=23)), thread_id=str(UUID(int=24)))
        catalog["projects"].append(second)
        self.config.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, "conflicting current coordinator bindings"):
            registrations(self.config)

        current = self.reg["coordinator_id"]
        catalog["workspace_coordinators"] = {self.reg["instance_id"]: {self.reg["workspace_id"]: current}}
        self.config.write_text(json.dumps(catalog))
        with self.assertRaisesRegex(ValueError, "current case must use the appointed workspace coordinator"):
            registrations(self.config, require_workspace_coordinators=True)

        second["defaults"]["notifications_enabled"] = False
        self.config.write_text(json.dumps(catalog))
        current_reg, historical_reg = registrations(self.config, require_workspace_coordinators=True)
        self.assertEqual(current_reg["coordinator_id"], current)
        self.assertEqual(historical_reg["coordinator_id"], alternate)
        self.assertFalse(historical_reg["notifications_enabled"])

        second["defaults"].update(workspace_id=str(UUID(int=25)), notifications_enabled=True)
        catalog["workspace_coordinators"][self.reg["instance_id"]][second["defaults"]["workspace_id"]] = alternate
        self.config.write_text(json.dumps(catalog))
        current_reg, other_workspace_reg = registrations(self.config, require_workspace_coordinators=True)
        self.assertEqual(current_reg["roles"]["coordinator"]["name"], other_workspace_reg["roles"]["coordinator"]["name"])
        self.assertEqual(other_workspace_reg["coordinator_id"], alternate)

    def test_prepare_note_formats_only_the_reviewed_snapshot(self):
        self.write_catalog()
        snapshot_file = self.config.with_name("snapshot.json")
        snapshot_file.write_text(json.dumps(self.snapshot))
        output = io.StringIO()
        with redirect_stdout(output), patch("unblock.__main__.datetime", wraps=datetime) as wall:
            wall.now.return_value = self.clock()
            self.assertEqual(main(["prepare-note", "--config", str(self.config), "--issue",
                                   self.reg["issue_id"], "--snapshot", str(snapshot_file)]), 0)
        self.assertTrue(output.getvalue().startswith("/note unblock.v1 "))
        self.assertEqual(json.loads(output.getvalue().removeprefix("/note unblock.v1 ")), self.snapshot)
        self.assertFalse(self.db.exists())
