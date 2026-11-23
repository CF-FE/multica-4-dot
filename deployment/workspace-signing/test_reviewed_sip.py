import codecs
from hashlib import sha256
import unittest

from reviewed_sip import verify_reviewed_sip
from test_sign_release import PACKET


SOURCE = b'Write-Output "multica-signing-fixture"\n'
SOURCE_HASH = "da3f28fe9a73ed89458cc9741c647b193f74363987078f1f7918177d363d6621"


def packet_for(canonical):
    return PACKET[:116] + sha256(canonical).digest() + PACKET[-2:]


class ReviewedSIPTests(unittest.TestCase):
    def test_independent_ascii_digest_matches_extracted_fixture(self):
        verify_reviewed_sip(SOURCE, SOURCE_HASH, PACKET)

    def test_bom_and_line_endings_remain_in_the_digest(self):
        text = 'Write-Output "审批样本 Ω🌱"\r\n'
        canonical = codecs.BOM_UTF16_LE + text.encode("utf-16-le")
        packet = packet_for(canonical)
        for source in (codecs.BOM_UTF8 + text.encode("utf-8"), canonical):
            verify_reviewed_sip(source, sha256(source).hexdigest(), packet)
            for different in (canonical[2:], canonical.replace(b"\r\0", b"")):
                with self.assertRaisesRegex(ValueError, "identifies different"):
                    verify_reviewed_sip(source, sha256(source).hexdigest(), packet_for(different))

    def test_rejects_win_worker_substitution_after_operator_approval(self):
        substituted = SOURCE.replace(b"fixture", b"replacement").decode().encode("utf-16-le")
        with self.assertRaisesRegex(ValueError, "identifies different"):
            verify_reviewed_sip(SOURCE, SOURCE_HASH, packet_for(substituted))
        with self.assertRaisesRegex(ValueError, "approved SHA-256"):
            verify_reviewed_sip(SOURCE + b" ", SOURCE_HASH, PACKET)

    def test_requires_canonical_indirect_data(self):
        for packet in (PACKET + b"\n", PACKET[:69] + b"\0" + PACKET[70:]):
            with self.assertRaisesRegex(ValueError, "canonical PowerShell"):
                verify_reviewed_sip(SOURCE, SOURCE_HASH, packet)

    def test_rejects_signature_markers_and_ambiguous_encodings(self):
        invalid = (b"\xff\xfeT", b"\xef\xbb\xbf\xff", b"\xc1", b"\x00ASCII",
                   b'# SIG # Begin signature block\nWrite-Output "noise"',
                   b"# SIG # Begin signature block suffix\n", b"# SIG # End signature block")
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(ValueError):
                verify_reviewed_sip(source, sha256(source).hexdigest(), PACKET)


if __name__ == "__main__":
    unittest.main()
