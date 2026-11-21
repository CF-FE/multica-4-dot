"""Read-only evidence for a single source and copy."""

import errno
import hashlib
import os
import re
import stat
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple


_UNSAFE_NAME = re.compile(r'[<>:"|?*\x00-\x1f\x7f\ud800-\udfff]')
_DEVICE_NAME = re.compile(r"(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³])", re.I)


class _ProbeError(Exception):
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason


class _FileSignature(NamedTuple):
    identity: tuple[int, int]
    mode: int
    size: int
    modified_ns: int
    metadata_ns: int
    attributes: int | None


def _safe_component(name):
    return (bool(name) and not name.endswith((" ", ".")) and not _UNSAFE_NAME.search(name)
            and not _DEVICE_NAME.fullmatch(name.split(".", 1)[0].rstrip(" ")))


def _windows_open(stack, path, directory):
    from ctypes import WinDLL, WinError, get_last_error, wintypes
    from msvcrt import open_osfhandle

    kernel = WinDLL("kernel32", use_last_error=True)
    create_file = kernel.CreateFileW
    create_file.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create_file.restype = wintypes.HANDLE
    close_handle = kernel.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    read_attributes, generic_read = 0x80, 0x80000000
    share_read, share_write = 1, 2
    open_existing, open_reparse_point, backup_semantics = 3, 0x00200000, 0x02000000
    # Hold the ancestors without sharing delete. Files also exclude concurrent write opens.
    handle = create_file(str(path), read_attributes if directory else generic_read,
                         share_read | share_write if directory else share_read, None,
                         open_existing, open_reparse_point | backup_semantics, None)
    if handle == wintypes.HANDLE(-1).value:
        error = get_last_error()
        if error in (2, 3):  # ERROR_FILE_NOT_FOUND or ERROR_PATH_NOT_FOUND
            raise FileNotFoundError
        raise WinError(error)
    try:
        fd = open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        close_handle(handle)
        raise
    stack.callback(os.close, fd)
    return fd


def _signature(info, directory):
    attributes = getattr(info, "st_file_attributes", None)
    if stat.S_ISLNK(info.st_mode) or (attributes or 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise _ProbeError("unsafe_path", "link_or_reparse_point")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode):
        raise _ProbeError("unsafe_path", "unexpected_file_type")
    if not info.st_ino or (os.name == "nt" and attributes is None):
        raise _ProbeError("unknown", "file_identity_unavailable")
    identity = (info.st_dev, info.st_ino)
    if directory:
        return identity
    if info.st_nlink > 1:
        raise _ProbeError("unsafe_path", "hard_link")
    if info.st_nlink != 1:
        raise _ProbeError("unknown", "link_count_unavailable")
    return _FileSignature(identity, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                          attributes)


def _scan(stack, root, parts):
    """Open each component without following links and record the path's identities."""
    if os.name != "nt" and (os.open not in os.supports_dir_fd
                            or os.stat not in os.supports_dir_fd
                            or os.stat not in os.supports_follow_symlinks
                            or not all(hasattr(os, flag) for flag in
                                       ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))):
        raise _ProbeError("unknown", "no_follow_unavailable")

    path = Path(root.anchor)
    names = (root.anchor, *root.parts[1:], *parts)
    signatures = []
    fd = None
    for index, name in enumerate(names):
        directory = index < len(names) - 1
        if index:
            path /= name
        try:
            if os.name == "nt":
                opened = _windows_open(stack, path, directory)
                signature = _signature(os.fstat(opened), directory)
            else:
                before = _signature(os.stat(name, dir_fd=fd, follow_symlinks=False), directory)
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if directory:
                    flags |= os.O_DIRECTORY
                try:
                    opened = os.open(name, flags, dir_fd=fd)
                except OSError as exc:
                    if exc.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                        raise _ProbeError("changed", "path_changed_during_open") from exc
                    raise
                stack.callback(os.close, opened)
                signature = _signature(os.fstat(opened), directory)
                if before != signature:
                    raise _ProbeError("changed", "path_changed_during_open")
        except FileNotFoundError:
            if index < len(root.parts):
                raise _ProbeError("unknown", "root_missing") from None
            return tuple(signatures), None
        signatures.append(signature)
        fd = opened
    return tuple(signatures), fd


def _read_digest(fd, size):
    digest = hashlib.sha256()
    count = 0
    # Read at most one byte beyond the initial size if a writer keeps appending.
    while count <= size:
        block = os.read(fd, min(1024 * 1024, size + 1 - count))
        if not block:
            break
        count += len(block)
        digest.update(block)
    if count != size:
        raise _ProbeError("changed", "size_changed_during_read")
    return {"bytes": count, "sha256": digest.hexdigest()}


def verify_copy(source_root, source_relative, target_root, target_relative,
                expected_bytes, expected_sha256) -> dict:
    """Return a JSON-ready observation of one copy using read-only file handles."""
    evidence = {"source": {}, "target": {}}
    if (type(expected_bytes) is not int or expected_bytes < 0 or not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256)):
        return {"status": "invalid_input", "reason": "invalid_expectation", "evidence": evidence}
    expected = {"bytes": expected_bytes, "sha256": expected_sha256.lower()}
    roots_and_parts = {}
    try:
        for subject, root, relative in (("source", source_root, source_relative),
                                        ("target", target_root, target_relative)):
            parts = re.split(r"[/\\]", relative) if isinstance(relative, str) else ()
            if not parts or not all(map(_safe_component, parts)):
                raise _ProbeError("unsafe_path", "invalid_relative_path")
            evidence[subject]["relative_path"] = "/".join(parts)
            root = Path(root)
            if not root.is_absolute() or ".." in root.parts or "\x00" in str(root):
                raise _ProbeError("unsafe_path", "invalid_root")
            if os.name == "nt":
                if not re.fullmatch(r"[A-Za-z]:", root.drive):
                    raise _ProbeError("unknown", "unsupported_windows_root")
                if not all(map(_safe_component, root.parts[1:])):
                    raise _ProbeError("unsafe_path", "invalid_root")
            roots_and_parts[subject] = (root, parts)
    except (TypeError, ValueError):
        return {"status": "invalid_input", "subject": subject, "reason": "invalid_root",
                "evidence": evidence}
    except _ProbeError as exc:
        return {"status": exc.status, "subject": subject, "reason": exc.reason, "evidence": evidence}

    observations = {}
    try:
        with ExitStack() as opened:
            scans = {}
            for subject, location in roots_and_parts.items():
                scans[subject] = _scan(opened, *location)
            source_signature, source_fd = scans["source"]
            target_signature, target_fd = scans["target"]
            if source_fd is not None and target_fd is not None:
                if source_signature[-1].identity == target_signature[-1].identity:
                    raise _ProbeError("unsafe_path", "same_file")

            for subject, (signatures, fd) in scans.items():
                if fd is not None:
                    observations[subject] = _read_digest(fd, signatures[-1].size)

            for subject, location in roots_and_parts.items():
                signatures, fd = scans[subject]
                try:
                    with ExitStack() as checked:
                        latest, _ = _scan(checked, *location)
                        # Compare the path before the old handle, which may have been unlinked.
                        if latest != signatures:
                            raise _ProbeError("changed", "path_or_file_changed")
                        if fd is not None:
                            info = os.fstat(fd)
                            if info.st_nlink == 0 or _signature(info, False) != signatures[-1]:
                                raise _ProbeError("changed", "path_or_file_changed")
                except _ProbeError as exc:
                    if exc.status == "unsafe_path" or exc.reason == "root_missing":
                        raise _ProbeError("changed", "path_or_file_changed") from exc
                    raise
    except _ProbeError as exc:
        return {"status": exc.status, "subject": subject, "reason": exc.reason, "evidence": evidence}
    except (OSError, NotImplementedError, ImportError, UnicodeError) as exc:
        return {"status": "unknown", "subject": subject, "reason": "filesystem_check_failed",
                "error_code": getattr(exc, "winerror", None) or getattr(exc, "errno", None),
                "evidence": evidence}

    for subject, observation in observations.items():
        evidence[subject].update(observation)
    if source_fd is None:
        status = "source_missing"
    elif observations["source"] != expected:
        status = "source_mismatch"
    elif target_fd is None:
        status = "not_copied"
    elif observations["target"]["bytes"] != expected_bytes:
        status = "size_mismatch"
    elif observations["target"]["sha256"] != expected["sha256"]:
        status = "digest_mismatch"
    else:
        status = "match_existing"
    return {"status": status, "evidence": evidence}
