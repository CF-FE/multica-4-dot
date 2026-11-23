"""Compare PowerShell indirect data to independently reviewed source bytes."""

import codecs
from hashlib import sha256
import re

from sign_release import ReleaseError, embedded_script_digest


MAX_SOURCE_BYTES = 1024 * 1024
SIGNATURE_MARKER = re.compile(r"#[ \t]*SIG[ \t]*#[ \t]*(?:Begin|End) signature block", re.I)


def verify_reviewed_sip(source: bytes, expected_source_sha256: str, indirect: bytes) -> None:
    """Fail before signing if the Windows digest does not identify the reviewed script."""
    if not 1 <= len(source) <= MAX_SOURCE_BYTES:
        raise ValueError("reviewed PowerShell source size is outside the supported range")
    if sha256(source).hexdigest() != expected_source_sha256:
        raise ValueError("reviewed source does not match the approved SHA-256")
    try:
        if source.startswith(codecs.BOM_UTF16_LE):
            text = source.decode("utf-16-le")
            canonical = source
        else:
            encoding = "utf-8" if source.startswith(codecs.BOM_UTF8) else "ascii"
            text = source.decode(encoding)
            # The 2.16 script SIP hashes the original line endings and all
            # UTF-16LE code units, including an original BOM as U+FEFF.
            # https://github.com/mtrojnar/osslsigncode/blob/2.16/script.c
            canonical = text.encode("utf-16-le")
    except UnicodeError:
        raise ValueError("reviewed source must be ASCII, UTF-8 BOM or UTF-16LE BOM") from None
    if "\0" in text or SIGNATURE_MARKER.search(text):
        raise ValueError("reviewed source contains a NUL or signature delimiter")
    try:
        expected_digest = embedded_script_digest(indirect)
    except ReleaseError as error:
        raise ValueError(str(error)) from None
    if sha256(canonical).digest() != expected_digest:
        raise ValueError("PowerShell indirect data identifies different source bytes")
