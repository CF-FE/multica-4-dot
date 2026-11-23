import base64
import codecs
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import workspace_sign as signing


class WorkspaceSigningClientTest(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.args = SimpleNamespace(
            project="be3d81b3-9bbd-4b58-98f6-6180911cea96",
            issue="01a1f9b0-ab24-7cf1-b748-8b5dc2c4e966",
            osslsigncode=Path("tool"),
            source=self.root / "sample.ps1",
            output=self.root / "sample.signed.ps1",
            request=self.root / "prepare.json",
            signature=self.root / "signature.der",
            certificate=self.root / "publisher.cer",
        )
        self.source = b"Write-Output 'cloud-work signing fixture'\r\n"
        self.args.source.write_bytes(self.source)
        self.args.expected_sha256 = signing.sha256(self.source)
        self.sip = b"test DER signing data"
        self.signature = b"test DER signature"
        self.cert = b"\x30fixture public certificate"
        self.args.signature.write_bytes(self.signature)
        self.args.certificate.write_bytes(self.cert)

    def fake_osslsigncode(self, command, label, *, cwd):
        if command[1] == "extract-data":
            (cwd / "sip.der").write_bytes(self.sip)
        elif command[1] == "attach-signature":
            staged = (cwd / "source.ps1").read_bytes()
            (cwd / "signed.ps1").write_bytes(staged + signing.append_block(self.signature, "ascii"))
        else:
            self.fail(f"unexpected subprocess {label}")

    @patch.object(signing, "run_tool", autospec=True)
    def test_prepare_binds_exact_source_and_request_can_be_read_back(self, tool):
        tool.side_effect = self.fake_osslsigncode
        request = signing.prepare(self.args)
        self.assertEqual(signing.read_request(self.args.request), (request, self.sip))
        self.assertEqual(request["project_id"], self.args.project)
        self.assertEqual(request["issue_id"], self.args.issue)
        self.assertEqual(request["source_sha256"], self.args.expected_sha256)
        self.assertEqual(signing.prepare(self.args), request)
        self.args.source.write_bytes(self.source + b"# changed")
        with self.assertRaisesRegex(ValueError, "approved SHA-256"):
            signing.prepare(self.args)

    def test_rejects_unmarked_multibyte_source_and_previous_signature(self):
        text = "# 凡人\r\n".encode("utf-8")
        for data, reason in ((text, "BOM-marked"), (self.source + signing.append_block(self.signature, "ascii"), "signature block")):
            self.args.source.write_bytes(data)
            with self.assertRaisesRegex(ValueError, reason):
                signing.read_source(self.args.source, signing.sha256(data))
        for data, codec in ((codecs.BOM_UTF8 + text, "utf-8"), (codecs.BOM_UTF16_LE + "# 凡人\r\n".encode("utf-16-le"), "utf-16-le")):
            self.args.source.write_bytes(data)
            self.assertEqual(signing.read_source(self.args.source, signing.sha256(data)), (data, codec))

    @patch.object(signing, "verify_windows", autospec=True)
    @patch.object(signing, "run_tool", autospec=True)
    def test_attach_checks_publisher_and_is_idempotent_without_overwriting(self, tool, verify):
        tool.side_effect = self.fake_osslsigncode
        signing.prepare(self.args)
        receipt = signing.attach(self.args)
        digest = signing.sha256(self.cert)
        self.assertEqual(verify.call_args.args[1], digest)
        self.assertEqual(receipt["certificate_sha256"], digest)
        self.assertEqual(receipt["signed_sha256"], signing.sha256(self.args.output.read_bytes()))
        self.assertEqual(self.args.source.read_bytes(), self.source)
        self.assertEqual(signing.attach(self.args), receipt)
        self.args.output.write_bytes(b"existing unrelated output")
        with self.assertRaisesRegex(ValueError, "output already exists"):
            signing.attach(self.args)
        self.assertEqual(self.args.output.read_bytes(), b"existing unrelated output")

    @patch.object(signing, "verify_windows", autospec=True)
    @patch.object(signing, "run_tool", autospec=True)
    def test_invalid_trust_or_mismatched_sip_cannot_publish(self, tool, verify):
        tool.side_effect = self.fake_osslsigncode
        signing.prepare(self.args)
        verify.side_effect = ValueError("Windows verification failed")
        with self.assertRaisesRegex(ValueError, "verification failed"):
            signing.attach(self.args)
        self.assertFalse(self.args.output.exists())
        request, _ = signing.read_request(self.args.request)
        substituted = b"different signing data"
        request["sip_der_base64"] = base64.b64encode(substituted).decode("ascii")
        request["sip_sha256"] = signing.sha256(substituted)
        self.args.request.write_text(json.dumps(request), encoding="ascii")
        with self.assertRaisesRegex(ValueError, "differs from the request"):
            signing.attach(self.args)
        self.assertFalse(self.args.output.exists())


if __name__ == "__main__":
    unittest.main()
