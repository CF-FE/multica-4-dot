import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from unblock.appointment import AppointmentUnavailable, bind_appointment, read_appointment
from unblock.__main__ import main, registrations


WORKSPACE = "00000000-0000-4000-8000-000000000001"
AGENT = "00000000-0000-4000-8000-000000000002"
SOURCE = "/etc/multica-unblock/appointment-ssh.conf"
RECORD = {"instance_id": "tencent", "workspace_id": WORKSPACE, "coordinator_id": AGENT,
          "generation": "1234" * 8, "confirmed_since": "2026-10-01T00:00:00.000000Z"}


class AppointmentTest(unittest.TestCase):
    def test_only_the_expected_authenticated_reply_can_supply_a_new_role(self):
        with patch("unblock.appointment.subprocess.run") as ssh:
            ssh.return_value.stdout = json.dumps(RECORD).encode()
            actual = read_appointment(SOURCE, "tencent", WORKSPACE)
        self.assertEqual(ssh.call_args.args[0][-4:], ["unblock-appointment", "read-appointment", "tencent", WORKSPACE])
        old = {"coordinator_id": WORKSPACE, "roles": {"coordinator": {"id": WORKSPACE}, "acceptor": {"id": "kept"}}}
        new = bind_appointment(old, actual)
        self.assertEqual(new["roles"]["coordinator"]["id"], AGENT)
        self.assertEqual(new["roles"]["coordinator"]["valid_from"], RECORD["confirmed_since"])
        self.assertIn(RECORD["generation"], new["roles"]["coordinator"]["appointment_ref"])
        self.assertEqual(new["roles"]["acceptor"], old["roles"]["acceptor"])
        self.assertEqual(old["coordinator_id"], WORKSPACE)

    def test_unknown_scope_clock_and_transport_all_defer(self):
        bad = [b"{}", b"[]", b"x" * 2049, b'{"coordinator_id":"a","coordinator_id":"b"}',
               *(json.dumps({**RECORD, **delta}).encode() for delta in (
                   {"instance_id": "other"}, {"workspace_id": AGENT}, {"coordinator_id": "name"},
                   {"confirmed_since": "2999-01-01T00:00:00Z"}, {"generation": "unknown"}))]
        with patch("unblock.appointment.subprocess.run") as ssh:
            for response in bad:
                ssh.return_value.stdout = response
                with self.subTest(response=response[:32]), self.assertRaises(AppointmentUnavailable):
                    read_appointment(SOURCE, "tencent", WORKSPACE)
            ssh.side_effect = subprocess.TimeoutExpired("ssh", 8)
            with self.assertRaises(AppointmentUnavailable):
                read_appointment(SOURCE, "tencent", WORKSPACE)

    def test_production_requires_live_authority_and_never_uses_cached_uuid(self):
        project = {"defaults": {"instance_id": "tencent", "workspace_id": WORKSPACE, "project_id": AGENT,
                                "coordinator_id": WORKSPACE},
                   "cases": [{"issue_id": WORKSPACE, "thread_id": AGENT, "notifications_enabled": True}]}
        with tempfile.TemporaryDirectory() as path:
            config = Path(path) / "cases.json"
            config.write_text(json.dumps({"projects": [project]}))
            with self.assertRaisesRegex(ValueError, "live workspace"):
                registrations(config, require_live_appointments=True)
            config.write_text(json.dumps({"projects": [project], "appointment_ssh_config": SOURCE}))
            case, = registrations(config, require_live_appointments=True)
            self.assertNotIn("coordinator_id", case)
            self.assertEqual(case["appointment_ssh_config"], SOURCE)

    def test_scan_groups_reads_by_workspace_and_does_not_send_on_failure(self):
        r = {"instance_id": "tencent", "workspace_id": WORKSPACE, "project_id": AGENT,
             "issue_id": WORKSPACE, "thread_id": AGENT, "roles": {}, "appointment_ssh_config": SOURCE}
        cases = [r, {**r, "issue_id": AGENT}]
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        args = ["tick", "--apply", "--db", str(Path(folder.name)/"ledger.db"), "--config", "/unused"]
        with patch("unblock.appointment.read_appointment", side_effect=AppointmentUnavailable("offline")) as read, \
                patch("unblock.__main__.run_case") as run, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args, registered=cases), 1)
            read.assert_called_once_with(SOURCE, "tencent", WORKSPACE)
            run.assert_not_called()
            self.assertEqual([c["reason"] for c in json.loads(out.getvalue())["cases"]],
                             ["coordinator_appointment_unconfirmed"] * 2)
        with patch("unblock.appointment.read_appointment", return_value=RECORD) as read, \
                patch("unblock.native.NativeSource"), patch("unblock.__main__.run_case") as run, \
                redirect_stdout(io.StringIO()):
            run.return_value = {"pending": [], "assessment": {"g8_status": "not_requested"}}
            self.assertEqual(main(args, registered=cases), 0)
            read.assert_called_once_with(SOURCE, "tencent", WORKSPACE)
            self.assertEqual([c.args[0]["coordinator_id"] for c in run.call_args_list], [AGENT, AGENT])
        with patch("unblock.appointment.read_appointment") as read, patch("unblock.native.NativeSource"), \
                patch("unblock.__main__.run_case") as run, redirect_stdout(io.StringIO()):
            run.return_value = {"pending": [], "assessment": {"g8_status": "not_requested"}}
            self.assertEqual(main(args, registered=cases), 0)
            read.assert_not_called()
            self.assertTrue(all(c.args[0]["_appointment_cached"] for c in run.call_args_list))
