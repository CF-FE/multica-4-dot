import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from unblock.artifact import verify_copy


class VerifyCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source_root = self.root / "source"
        self.target_root = self.root / "target"
        self.source_root.mkdir()
        self.target_root.mkdir()
        self.source = self.source_root / "item.bin"
        self.target = self.target_root / "copy.bin"
        self.content = b"fixture"
        self.digest = hashlib.sha256(self.content).hexdigest()
        self.source.write_bytes(self.content)

    def verify(self, *, source="item.bin", target="copy.bin", size=None, digest=None):
        return verify_copy(
            self.source_root, source, self.target_root, target,
            len(self.content) if size is None else size,
            self.digest if digest is None else digest,
        )

    def test_existing_copy_matches_with_relative_evidence(self):
        self.target.write_bytes(self.content)
        result = self.verify(digest=self.digest.upper())
        self.assertEqual(result["status"], "match_existing")
        self.assertEqual(result["evidence"]["source"], {
            "relative_path": "item.bin", "bytes": len(self.content), "sha256": self.digest,
        })
        self.assertEqual(result["evidence"]["target"], {
            "relative_path": "copy.bin", "bytes": len(self.content), "sha256": self.digest,
        })
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_missing_target_stays_missing(self):
        result = self.verify(target="new/copy.bin")
        self.assertEqual(result["status"], "not_copied")
        self.assertFalse((self.target_root / "new").exists())
        self.assertEqual(result["evidence"]["target"], {"relative_path": "new/copy.bin"})

    def test_empty_file_matches(self):
        self.source.write_bytes(b"")
        self.target.write_bytes(b"")
        self.assertEqual(self.verify(size=0, digest=hashlib.sha256().hexdigest())["status"],
                         "match_existing")

    def test_binary_copy_spans_multiple_read_blocks(self):
        content = b"\r\n\x1a\x00" * (256 * 1024 + 1)
        self.source.write_bytes(content)
        self.target.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        result = self.verify(size=len(content), digest=digest)
        self.assertEqual(result["status"], "match_existing")
        self.assertEqual(result["evidence"]["target"]["sha256"], digest)

    def test_equal_size_with_wrong_digest(self):
        wrong_content = b"another"
        self.target.write_bytes(wrong_content)
        result = self.verify()
        self.assertEqual(result["status"], "digest_mismatch")
        self.assertEqual(result["evidence"]["target"]["sha256"],
                         hashlib.sha256(wrong_content).hexdigest())

    def test_size_mismatch(self):
        self.target.write_bytes(b"short")
        result = self.verify()
        self.assertEqual(result["status"], "size_mismatch")
        self.assertEqual(result["evidence"]["target"]["bytes"], 5)

    def test_source_does_not_match_expectation(self):
        self.target.write_bytes(self.content)
        self.source.write_bytes(b"another")
        self.assertEqual(self.verify()["status"], "source_mismatch")

    def test_untrusted_relative_paths_are_rejected_without_echo(self):
        for path in (str(self.root / "secret"), "../secret", "a/../secret", "C:secret",
                     "C:\\secret", "\\secret", "//server/share", "copy.bin:stream",
                     ".. /secret", "NUL.txt", "\ud800"):
            with self.subTest(path=path):
                result = self.verify(target=path)
                self.assertEqual(result["status"], "unsafe_path")
                self.assertNotIn("relative_path", result["evidence"]["target"])

    def test_invalid_expectations_are_rejected(self):
        for size, digest in ((True, self.digest), (-1, self.digest), (1, "not-a-digest")):
            with self.subTest(size=size, digest=digest):
                self.assertEqual(self.verify(size=size, digest=digest)["status"], "invalid_input")

    def test_symlink_at_file_or_parent_is_rejected(self):
        try:
            self.target.symlink_to(self.source)
            (self.target_root / "linked").symlink_to(self.source_root, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"fixture cannot create symlinks ({type(exc).__name__})")
        self.assertEqual(self.verify()["status"], "unsafe_path")
        self.assertEqual(self.verify(target="linked/item.bin")["status"], "unsafe_path")

    def test_symlink_at_configured_root_is_rejected(self):
        alias_root = self.root / "alias"
        try:
            alias_root.symlink_to(self.source_root, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"fixture cannot create symlinks ({type(exc).__name__})")
        result = verify_copy(alias_root, "item.bin", self.target_root, "copy.bin",
                             len(self.content), self.digest)
        self.assertEqual((result["status"], result["subject"]), ("unsafe_path", "source"))

    def test_directory_in_place_of_target_file_is_rejected(self):
        self.target.mkdir()
        result = self.verify()
        self.assertEqual((result["status"], result["reason"]),
                         ("unsafe_path", "unexpected_file_type"))

    def test_same_file_with_overlapping_roots_is_rejected(self):
        result = verify_copy(self.root, "source/item.bin", self.source_root, "item.bin",
                             len(self.content), self.digest)
        self.assertEqual(result["status"], "unsafe_path")

    def test_hard_links_on_either_side_are_rejected(self):
        try:
            os.link(self.source, self.target)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"fixture cannot create hard links ({type(exc).__name__})")
        self.assertEqual(self.verify()["status"], "unsafe_path")
        self.target.unlink()
        self.target.write_bytes(self.content)
        os.link(self.target, self.target_root / "other.bin")
        result = self.verify()
        self.assertEqual(result["status"], "unsafe_path")
        self.assertEqual(result["subject"], "target")

    def test_missing_source_and_missing_probe_root_are_distinct(self):
        self.assertEqual(self.verify(source="absent.bin")["status"], "source_missing")
        self.target_root.rmdir()
        self.assertEqual(self.verify()["status"], "unknown")

    def test_missing_file_identity_is_unknown(self):
        with patch("unblock.artifact.os.fstat", return_value=SimpleNamespace(
            st_mode=self.source_root.stat().st_mode, st_ino=0,
        )):
            result = self.verify()
        self.assertEqual((result["status"], result["reason"]),
                         ("unknown", "file_identity_unavailable"))

    def test_os_error_does_not_disclose_absolute_paths(self):
        with patch("unblock.artifact.os.fstat", side_effect=PermissionError(
            13, "access denied", str(self.root),
        )):
            result = self.verify()
        self.assertEqual((result["status"], result["error_code"]), ("unknown", 13))
        self.assertNotIn(str(self.root), json.dumps(result))

    @unittest.skipUnless(os.name == "posix", "requires POSIX inode replacement semantics")
    def test_source_replaced_after_first_hash_is_changed(self):
        self.target.write_bytes(self.content)
        replacement = self.source_root / "replacement.bin"
        replacement.write_bytes(self.content)
        make_sha256 = hashlib.sha256
        attempts = 0

        def replace_while_hashing():
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                replacement.replace(self.source)
            return make_sha256()

        with patch("unblock.artifact.hashlib.sha256", side_effect=replace_while_hashing):
            result = self.verify()
        self.assertEqual((result["status"], result["subject"]), ("changed", "source"))
        self.assertNotIn("sha256", result["evidence"]["source"])

    @unittest.skipUnless(os.name == "posix", "requires POSIX writes during read")
    def test_target_rewritten_in_place_is_changed(self):
        self.target.write_bytes(self.content)
        previous = self.target.stat()
        make_sha256 = hashlib.sha256
        attempts = 0

        def write_while_hashing():
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                self.target.write_bytes(b"another")
                os.utime(self.target, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            return make_sha256()

        with patch("unblock.artifact.hashlib.sha256", side_effect=write_while_hashing):
            result = self.verify()
        self.assertEqual((result["status"], result["subject"]), ("changed", "target"))

    def test_target_appearing_while_source_is_read_is_changed(self):
        make_sha256 = hashlib.sha256

        def copy_while_hashing():
            self.target.write_bytes(self.content)
            return make_sha256()

        with patch("unblock.artifact.hashlib.sha256", side_effect=copy_while_hashing):
            result = self.verify()
        self.assertEqual((result["status"], result["subject"]), ("changed", "target"))


if __name__ == "__main__":
    unittest.main()
