"""Run with python3 -m unittest discover -s deployment/workspace-signing."""

import base64
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import sign_release as signer


# osslsigncode extract-data -h sha256 for a harmless PowerShell fixture.
PACKET = base64.b64decode(
    "MIGTBgkqhkiG9w0BBwKggYUwgYICAQExADB5BgorBgEEAYI3AgEEoGswaTA0BgorBgEEAYI3AgEe"
    "MCYCAwEAAAQQH8w7YFlLCE63JNLGKX7zUQIBAAIBAAIBAAIBAAIBADAxMA0GCWCGSAFlAwQCAQUABCDc"
    "Ayw0+zgOOffUcl4r/4bq/FpfAWzh2jGUqIu5gJcj3TEA"
)
PACKET_HASH = "9fed2b31b1af3742f2c8099d7c7f749fdfedbe26dda5c9863f9bd421309f94f6"
PROJECT = "00000000-0000-4000-8000-000000000001"
ISSUE = "00000000-0000-4000-8000-000000000002"
ACTOR = "00000000-0000-4000-8000-000000000003"
SOURCE = "a" * 64


class RequestTests(unittest.TestCase):
    def test_extract_data_packet(self):
        self.assertEqual(
            signer.read_request(BytesIO(b"mul_example\n" + PACKET), PACKET_HASH),
            ("mul_example", PACKET),
        )

    def test_changed_content_requires_new_operator_digest(self):
        altered = PACKET[:116] + b"X" + PACKET[117:]
        with self.assertRaisesRegex(signer.ReleaseError, "operator-approved"):
            signer.read_request(BytesIO(b"mul_example\n" + altered), PACKET_HASH)

    def test_rejects_non_powershell_sip_and_trailing_bytes_even_when_approved(self):
        different_sip = PACKET[:69] + b"\x00" + PACKET[70:]
        for invalid in (different_sip, PACKET[:-1], PACKET + b"\n"):
            with self.subTest(length=len(invalid)):
                with self.assertRaisesRegex(signer.ReleaseError, "canonical PowerShell"):
                    signer.read_request(BytesIO(b"mul_example\n" + invalid), sha256(invalid).hexdigest())

    def test_rejects_header_injection_oversized_or_missing_token(self):
        for header in (b"token\r\n", b"x" * 1025 + b"\n", b"\n", b"token"):
            with self.subTest(length=len(header)):
                with self.assertRaisesRegex(signer.ReleaseError, "bounded bearer"):
                    signer.read_request(BytesIO(header + PACKET), PACKET_HASH)


class NativeScopeTests(unittest.TestCase):
    def setUp(self):
        self.project_path = f"/api/projects/{PROJECT}"
        self.issue_path = f"/api/issues/{ISSUE}"
        self.rows = {
            "/api/me": {"id": ACTOR},
            self.project_path: {"id": PROJECT, "workspace_id": signer.WORKSPACE, "archived_at": None},
            self.issue_path: {"id": ISSUE, "workspace_id": signer.WORKSPACE, "project_id": PROJECT},
        }

    def test_lookup_checks_authenticated_actor_and_original_issue(self):
        self.assertEqual(signer.verify_scope(PROJECT, ISSUE, self.rows.__getitem__), ACTOR)

    def test_project_or_original_issue_scope_mismatch_is_rejected(self):
        for path, field in (
            (self.project_path, "workspace_id"),
            (self.project_path, "archived_at"),
            (self.issue_path, "workspace_id"),
            (self.issue_path, "project_id"),
        ):
            original = self.rows[path][field]
            self.rows[path][field] = "different"
            with self.subTest(path=path, field=field):
                with self.assertRaises(signer.ReleaseError):
                    signer.verify_scope(PROJECT, ISSUE, self.rows.__getitem__)
            self.rows[path][field] = original

    def test_localhost_redirect_is_denied_without_reading_body(self):
        with patch.object(signer, "HTTPConnection") as connect:
            conn = connect.return_value
            response = conn.getresponse.return_value.__enter__.return_value
            response.status = 307
            with self.assertRaisesRegex(signer.ReleaseError, "HTTP 307"):
                signer.native_get("/api/me", "mul_example")
            connect.assert_called_once_with("127.0.0.1", 8080, timeout=8)
            self.assertEqual(conn.request.call_count, 1)
            response.read.assert_not_called()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "releases.sqlite3"
        # Unit tests exercise the ledger without a root-owned test directory.
        permissions = patch.object(signer, "require_owned")
        permissions.start()
        self.addCleanup(permissions.stop)

    def release(self, sign, sip=PACKET_HASH):
        return signer.release(self.db, PROJECT, ISSUE, SOURCE, sip, ACTOR, sign)

    def test_replay_returns_stored_bytes_without_reissuing_signature(self):
        signature = b"test signature"

        def signed():
            return signature, "b" * 64

        self.assertEqual(self.release(signed), signature)
        self.assertEqual(self.release(lambda: self.fail("must not re-sign")), signature)
        with sqlite3.connect(self.db) as db:
            rows = db.execute(
                "SELECT api_actor_id, source_sha256, sip_sha256, signature_sha256 FROM releases"
            ).fetchall()
        self.assertEqual(rows, [(ACTOR, SOURCE, PACKET_HASH, sha256(signature).hexdigest())])

    def test_same_source_approval_rejects_a_different_packet(self):
        self.release(lambda: (b"test signature", "b" * 64))
        with self.assertRaisesRegex(signer.ReleaseError, "bound to a different indirect digest"):
            self.release(lambda: self.fail("must not re-sign"), sip="0" * 64)

    def test_failed_signer_leaves_no_release_and_does_not_block_retry(self):
        def failed():
            raise signer.ReleaseError("fake signer failure")

        with self.assertRaisesRegex(signer.ReleaseError, "fake signer failure"):
            self.release(failed)
        result = self.release(lambda: (b"test signature", "b" * 64))
        self.assertEqual(result, b"test signature")

    def test_ledger_returns_only_intact_signatures(self):
        self.release(lambda: (b"test signature", "b" * 64))
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE releases SET signature = ?", (b"unexpected data",))
        with self.assertRaisesRegex(signer.ReleaseError, "stored signature digest mismatch"):
            self.release(lambda: self.fail("must not re-sign"))


if __name__ == "__main__":
    unittest.main()
