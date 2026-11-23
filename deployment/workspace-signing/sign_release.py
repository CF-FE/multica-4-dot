#!/usr/bin/env python3
"""Operator-only signing of PowerShell Authenticode indirect data on Tencent."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import UUID


WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
STATE = Path("/var/lib/multica-workspace-signing")
SIGNER = Path("/usr/local/bin/osslsigncode")
MAX_TOKEN = 1024
MAX_RESPONSE = 1024 * 1024
MAX_SIGNATURE = 64 * 1024

# Canonical PKCS#7 SignedData emitted by osslsigncode extract-data for PowerShell
# and SHA-256. The SIP UUID identifies PowerShell. A single 32-byte OCTET STRING
# (the embedded script digest) is the only variable field.
PS1_PREFIX = bytes.fromhex(
    "30819306092a864886f70d010702a0818530818202010131003079060a2b060104018237020104"
    "a06b30693034060a2b06010401823702011e3026020301000004101fcc3b60594b084eb724d2c6"
    "297ef3510201000201000201000201000201003031300d060960864801650304020105000420"
)
PS1_SUFFIX = bytes.fromhex("3100")
SIP_SIZE = len(PS1_PREFIX) + 32 + len(PS1_SUFFIX)


class ReleaseError(Exception):
    pass


def check_uuid(value):
    try:
        if str(UUID(value)) == value:
            return value
    except (AttributeError, TypeError, ValueError):
        pass
    raise ReleaseError("expected a canonical UUID")


def check_sha256(value):
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ReleaseError("expected a lowercase SHA-256")
    return value


def embedded_script_digest(data):
    if (len(data) != SIP_SIZE or not data.startswith(PS1_PREFIX) or
            not data.endswith(PS1_SUFFIX)):
        raise ReleaseError("expected canonical PowerShell SHA-256 indirect data")
    return data[len(PS1_PREFIX):-len(PS1_SUFFIX)]


def read_request(stream, expected_sip_sha256):
    line = stream.readline(MAX_TOKEN + 2)
    token = line[:-1]
    if (not line.endswith(b"\n") or len(token) > MAX_TOKEN or
            not re.fullmatch(rb"[A-Za-z0-9._~+/-]+=*", token)):
        raise ReleaseError("expected a bounded bearer token before the DER packet")
    data = stream.read(SIP_SIZE + 1)
    embedded_script_digest(data)
    if sha256(data).hexdigest() != expected_sip_sha256:
        raise ReleaseError("indirect data differs from the operator-approved digest")
    return token.decode("ascii"), data


def native_get(path, token):
    # HTTPConnection never follows redirects or obtains a proxy from the environment.
    with closing(HTTPConnection("127.0.0.1", 8080, timeout=8)) as connection:
        try:
            connection.request("GET", path, headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "X-Workspace-ID": WORKSPACE,
            })
            with connection.getresponse() as response:
                if response.status != 200:
                    raise ReleaseError(f"native Multica scope check returned HTTP {response.status}")
                body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE:
                raise ReleaseError("native Multica scope response is too large")
            result = json.loads(body)
        except (HTTPException, OSError, ValueError):
            raise ReleaseError("could not read the native Multica scope") from None
    if not isinstance(result, dict):
        raise ReleaseError("unexpected native Multica scope response")
    return result


def verify_scope(project, issue, get):
    actor = check_uuid(get("/api/me").get("id"))
    native_project = get(f"/api/projects/{project}")
    if (native_project.get("id") != project or native_project.get("workspace_id") != WORKSPACE or
            native_project.get("archived_at") is not None):
        raise ReleaseError("project is unavailable in the signing workspace")
    native_issue = get(f"/api/issues/{issue}")
    if (native_issue.get("id") != issue or native_issue.get("workspace_id") != WORKSPACE or
            native_issue.get("project_id") != project):
        raise ReleaseError("issue is outside the approved project")
    return actor


def require_owned(path, kind, denied):
    info = path.lstat()
    if info.st_uid != 0 or not kind(info.st_mode) or info.st_mode & denied:
        raise ReleaseError(f"unsafe ownership or permissions for {path.name}")


def sign(state, data):
    require_owned(SIGNER, stat.S_ISREG, 0o022)
    key = state / "key.pem"
    cert = state / "cert.pem"
    require_owned(key, stat.S_ISREG, 0o077)
    require_owned(cert, stat.S_ISREG, 0o022)
    try:
        cert_sha256 = sha256(ssl.PEM_cert_to_DER_cert(cert.read_text("ascii"))).hexdigest()
    except ValueError:
        raise ReleaseError("publisher certificate is invalid") from None
    with TemporaryDirectory(prefix=".sign-", dir=state) as folder:
        unsigned = Path(folder) / "indirect.der"
        output = Path(folder) / "signature.der"
        unsigned.write_bytes(data)
        try:
            result = subprocess.run(
                [str(SIGNER), "sign", "-certs", str(cert), "-key", str(key),
                 "-h", "sha256", "-in", str(unsigned), "-out", str(output)],
                env={"LANG": "C", "PATH": "/usr/bin:/bin"},
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise ReleaseError("Authenticode signer timed out") from None
        if result.returncode:
            raise ReleaseError("Authenticode signer failed")
        with output.open("rb") as artifact:
            signature = artifact.read(MAX_SIGNATURE + 1)
    if not signature.startswith(b"\x30") or len(signature) > MAX_SIGNATURE:
        raise ReleaseError("Authenticode signer returned invalid output")
    return signature, cert_sha256


def release(db_path, project, issue, source, sip, actor, sign_once):
    """Return the persisted signature, or sign and persist within one transaction."""
    if db_path.is_symlink() or db_path.exists():
        require_owned(db_path, stat.S_ISREG, 0o077)
    with closing(sqlite3.connect(db_path, timeout=45)) as db, db:
        db.execute("PRAGMA synchronous = FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("""
            CREATE TABLE IF NOT EXISTS releases(
                project_id TEXT NOT NULL,
                issue_id TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                sip_sha256 TEXT NOT NULL,
                publisher_sha256 TEXT NOT NULL,
                signature_sha256 TEXT NOT NULL,
                signature BLOB NOT NULL,
                api_actor_id TEXT NOT NULL,
                signed_at TEXT NOT NULL,
                PRIMARY KEY (project_id, issue_id, source_sha256)
            )
        """)
        current = db.execute(
            "SELECT sip_sha256, signature_sha256, signature FROM releases "
            "WHERE project_id = ? AND issue_id = ? AND source_sha256 = ?",
            (project, issue, source),
        ).fetchone()
        if current is not None:
            stored_sip, stored_digest, signature = current
            if sip != stored_sip:
                raise ReleaseError("this source approval is bound to a different indirect digest")
            if sha256(signature).hexdigest() != stored_digest:
                raise ReleaseError("stored signature digest mismatch")
            return signature
        signature, publisher = sign_once()
        db.execute(
            "INSERT INTO releases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project, issue, source, sip, publisher, sha256(signature).hexdigest(), signature,
             actor, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return signature


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--source-sha256", required=True,
                        help="SHA-256 of the reviewed source from which the operator computed the SIP")
    parser.add_argument("--expected-sip-sha256", required=True)
    parser.add_argument("--token-stdin", action="store_true",
                        help="read the native Multica token, a newline, then the binary SIP from stdin")
    args = parser.parse_args()
    if not args.token_stdin:
        parser.error("--token-stdin is required")
    try:
        if os.geteuid() != 0:
            raise ReleaseError("release host root required")
        os.umask(0o077)
        require_owned(STATE, stat.S_ISDIR, 0o077)
        project = check_uuid(args.project)
        issue = check_uuid(args.issue)
        source = check_sha256(args.source_sha256)
        sip = check_sha256(args.expected_sip_sha256)
        token, data = read_request(sys.stdin.buffer, sip)
        actor = verify_scope(project, issue, lambda path: native_get(path, token))
        signature = release(STATE / "releases.sqlite3", project, issue, source, sip,
                            actor, lambda: sign(STATE, data))
        sys.stdout.buffer.write(signature)
        sys.stdout.buffer.flush()
    except ReleaseError as error:
        print(f"sign_release: {error}", file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error):
        print("sign_release: could not read the protected signing state or return the signature",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
