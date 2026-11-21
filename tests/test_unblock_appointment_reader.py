"""Isolated tests for the restricted coordinator appointment projection."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


PROJECTION_PATH = Path(__file__).resolve().parents[1] / "deployment/unblock/read-appointment.py"
SPEC = importlib.util.spec_from_file_location("unblock_appointment_reader", PROJECTION_PATH)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)

WORKSPACE = "1111111a-1111-4111-8111-111111111111"
OTHER_WORKSPACE = "22222222-2222-4222-8222-222222222222"
COORDINATOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
NEW_COORDINATOR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
INVOCATION = "1" * 32
ACTIVE = INVOCATION, "2026-11-20T15:54:43.124966Z", "123"
REQUEST = f"read-appointment tencent {WORKSPACE}\n"


class AppointmentReaderTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.allowed = Path(directory) / "allowed.json"
        self.disk = Path(directory) / "config.json"
        self.running = Path(directory) / "running.json"
        self.allowed.write_text(json.dumps([WORKSPACE]), encoding="utf-8")
        for path in self.disk, self.running:
            self.write_configuration(path, COORDINATOR)
        self.read_unit = Mock(return_value=ACTIVE)

    def write_configuration(self, path, coordinator):
        path.write_text(json.dumps({
            "instances": {
                "tencent": {"workspaces": {WORKSPACE: {"coordinator_id": coordinator}}},
                "other": {"workspaces": {WORKSPACE: {"coordinator_id": NEW_COORDINATOR}}},
            },
            "secret_fixture": "never echoed",
        }), encoding="utf-8")

    def resolve(self, request=REQUEST):
        return reader.read_appointment(request, self.allowed, self.disk, self.running, self.read_unit)

    def test_projects_only_approved_data_from_one_active_generation(self):
        self.assertEqual(self.resolve(), {
            "instance_id": "tencent",
            "workspace_id": WORKSPACE,
            "coordinator_id": COORDINATOR,
            "generation": INVOCATION,
            "confirmed_since": ACTIVE[1],
        })
        self.assertEqual(self.read_unit.call_count, 2)

    def test_rejects_wrong_target_and_noncanonical_command(self):
        for command in (f"read-appointment other {WORKSPACE}\n",
                        f"read-appointment tencent {OTHER_WORKSPACE}\n",
                        REQUEST.strip(), REQUEST + "extra\n",
                        REQUEST.replace("tencent ", "tencent  ")):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.resolve(command)
        self.read_unit.assert_not_called()

    def test_refuses_disk_change_then_returns_new_occupant_after_reload(self):
        self.write_configuration(self.disk, NEW_COORDINATOR)
        with self.assertRaisesRegex(ValueError, "disagrees"):
            self.resolve()
        self.write_configuration(self.running, NEW_COORDINATOR)
        self.read_unit.return_value = ("2" * 32, "2026-11-20T16:15:00.000001Z", "124")
        self.assertEqual(self.resolve()["coordinator_id"], NEW_COORDINATOR)

    def test_refuses_unit_generation_change(self):
        self.read_unit.side_effect = [ACTIVE, ("2" * 32, ACTIVE[1], "124")]
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve()

    def test_refuses_config_edit_between_snapshots(self):
        def second_snapshot():
            if self.read_unit.call_count == 2:
                self.write_configuration(self.disk, NEW_COORDINATOR)
            return ACTIVE

        self.read_unit.side_effect = second_snapshot
        with self.assertRaisesRegex(ValueError, "changed"):
            self.resolve()

    def test_rejects_duplicate_json_keys_and_noncanonical_coordinator(self):
        self.disk.write_text('{"instances":{},"instances":{}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.resolve()
        self.write_configuration(self.disk, COORDINATOR.upper())
        with self.assertRaisesRegex(ValueError, "invalid coordinator"):
            self.resolve()

    def test_rejects_an_alias_that_would_override_gateway_scope(self):
        document = json.loads(self.disk.read_text(encoding="utf-8"))
        document["instances"]["tencent"]["workspaces"][WORKSPACE.upper()] = {"coordinator_id": NEW_COORDINATOR}
        self.disk.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "invalid workspace"):
            self.resolve()

    def test_rejects_writable_or_symlink_grants(self):
        self.allowed.chmod(0o666)
        with self.assertRaisesRegex(ValueError, "permissions"):
            self.resolve()
        self.allowed.unlink()
        self.allowed.symlink_to(self.running)
        with self.assertRaises(OSError):
            self.resolve()

    def test_converts_systemd_utc_timestamp_and_rejects_inactive_unit(self):
        output = (
            "ActiveState=active\nSubState=running\n"
            "ActiveEnterTimestamp=Fri 2026-11-20 15:54:43.124966 UTC\n"
            f"ActiveEnterTimestampMonotonic=123\nInvocationID={INVOCATION}\n"
        )
        with patch.object(reader.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)):
            self.assertEqual(reader._read_active_unit(), ACTIVE)
        exited = subprocess.CompletedProcess([], 0, output.replace("SubState=running", "SubState=exited"))
        with patch.object(reader.subprocess, "run", return_value=exited), self.assertRaises(ValueError):
            reader._read_active_unit()


if __name__ == "__main__":
    unittest.main()
