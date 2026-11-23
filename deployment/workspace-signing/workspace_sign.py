#!/usr/bin/env python3
"""Prepare and verify detached Authenticode signatures for cloud-work .ps1 files."""

import argparse
import base64
import codecs
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from uuid import UUID


WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
INSTALL_ROOT = Path(r"C:\Program Files\Multica Workspace Signing")
SCRIPT_LIMIT = 1024 * 1024
SIGNATURE_LIMIT = 64 * 1024
SIP_LIMIT = 4096
REQUEST_LIMIT = 8192
REQUEST_FIELDS = {
    "workspace_id", "project_id", "issue_id", "filename", "source_sha256",
    "sip_sha256", "sip_der_base64",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def canonical_uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("expected a canonical UUID")
    return value


def digest_arg(value):
    if not isinstance(value, str) or not re.fullmatch("[a-fA-F0-9]{64}", value):
        raise ValueError("expected a SHA-256 hex digest")
    return value.lower()


def read_file(path, limit, label):
    with path.open("rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError(f"{label} must be a regular file")
        data = handle.read(limit + 1)
    if not 0 < len(data) <= limit:
        raise ValueError(f"{label} must contain 1 to {limit} bytes")
    return data


def read_source(path, expected_digest):
    if path.suffix.lower() != ".ps1":
        raise ValueError("source must have a .ps1 extension")
    data = read_file(path, SCRIPT_LIMIT, "source")
    if sha256(data) != digest_arg(expected_digest):
        raise ValueError("source does not match the approved SHA-256")
    if data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8"
        script = data.decode("utf-8-sig")
    elif data.startswith(codecs.BOM_UTF16_LE):
        encoding = "utf-16-le"
        script = data[len(codecs.BOM_UTF16_LE):].decode(encoding)
    else:
        encoding = "ascii"
        try:
            script = data.decode(encoding)
        except UnicodeDecodeError:
            raise ValueError("use ASCII, BOM-marked UTF-8, or BOM-marked UTF-16LE for Windows PowerShell") from None
    if "\0" in script:
        raise ValueError("source contains a null character")
    if re.search(r"(?im)^\s*#\s*SIG\s*#\s*(?:Begin|End) signature block\s*$", script):
        raise ValueError("source already contains an Authenticode signature block")
    return data, encoding


def read_request(path):
    def object_pairs(items):
        obj = dict(items)
        if len(obj) != len(items):
            raise ValueError("duplicate keys in signing request")
        return obj

    request = json.loads(read_file(path, REQUEST_LIMIT, "request"), object_pairs_hook=object_pairs)
    if not isinstance(request, dict) or set(request) != REQUEST_FIELDS or request["workspace_id"] != WORKSPACE:
        raise ValueError("invalid cloud-work signing request")
    canonical_uuid(request["project_id"])
    canonical_uuid(request["issue_id"])
    encoded = request["sip_der_base64"]
    if not isinstance(encoded, str):
        raise ValueError("invalid signing data")
    der = base64.b64decode(encoded, validate=True)
    if not 0 < len(der) <= SIP_LIMIT or sha256(der) != digest_arg(request["sip_sha256"]):
        raise ValueError("signing data does not match the request digest")
    return request, der


def run_tool(command, label, *, env=None, cwd):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=45)
    if result.returncode:
        raise ValueError(f"{label} failed with exit code {result.returncode}")
    return result.stdout


def extract_data(tool, directory, source):
    snapshot = directory / "source.ps1"
    snapshot.write_bytes(source)
    output = directory / "sip.der"
    run_tool(
        [str(tool), "extract-data", "-h", "sha256", "-in", str(snapshot), "-out", str(output)],
        "Authenticode data extraction", cwd=directory,
    )
    return read_file(output, SIP_LIMIT, "extracted signing data")


def append_block(signature, encoding):
    binary = base64.b64encode(signature).decode("ascii")
    records = [binary[start:start + 64] for start in range(0, len(binary), 64)]
    records = ["SIG # Begin signature block", *records, "SIG # End signature block"]
    return ("".join(f"\r\n# {line}" for line in records) + "\r\n").encode(encoding)


def verify_windows(path, publisher_digest):
    if os.name != "nt":
        raise ValueError("attach requires the Windows host that verifies the signature")
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = {**os.environ, "MULTICA_SIGNED_STAGING_PATH": str(path)}
    command = r"""
$ErrorActionPreference = 'Stop'
$signedPath = $env:MULTICA_SIGNED_STAGING_PATH
$sig = Microsoft.PowerShell.Security\Get-AuthenticodeSignature -LiteralPath $signedPath
if (($sig.Status -ne 'Valid') -or ($sig.SignatureType -ne 'Authenticode') -or (-not $sig.SignerCertificate)) {
    [Console]::Out.WriteLine('invalid')
    exit
}
$hash = [System.Security.Cryptography.SHA256]::Create()
try {
    [Console]::Out.WriteLine([BitConverter]::ToString($hash.ComputeHash($sig.SignerCertificate.RawData)).Replace('-', '').ToLowerInvariant())
} finally { $hash.Dispose() }
"""
    result = run_tool(
        [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        "Windows Authenticode verification", env=env, cwd=path.parent,
    )
    if result.strip() != publisher_digest.encode("ascii"):
        raise ValueError("Windows did not validate the embedded signature and pinned publisher")


def publish_file(staged, destination, expected, limit):
    try:
        if os.name == "nt":
            os.rename(staged, destination)  # Windows rename fails if the target exists.
        else:
            os.link(staged, destination)
    except FileExistsError:
        if destination.is_symlink() or read_file(destination, limit, "existing output") != expected:
            raise ValueError("output already exists with different content") from None
    if destination.is_symlink() or read_file(destination, limit, "published output") != expected:
        raise ValueError("published content differs from the verified file")


def prepare(args):
    source, _ = read_source(args.source, args.expected_sha256)
    project_id = canonical_uuid(args.project)
    issue_id = canonical_uuid(args.issue)
    with tempfile.TemporaryDirectory(dir=args.request.parent) as scratch:
        stage = Path(scratch).resolve()
        data = extract_data(args.osslsigncode, stage, source)
        request = {
            "workspace_id": WORKSPACE,
            "project_id": project_id,
            "issue_id": issue_id,
            "filename": args.source.name,
            "source_sha256": sha256(source),
            "sip_sha256": sha256(data),
            "sip_der_base64": base64.b64encode(data).decode("ascii"),
        }
        encoded = (json.dumps(request, ensure_ascii=True, indent=2) + "\n").encode("ascii")
        if len(encoded) > REQUEST_LIMIT:
            raise ValueError("encoded request exceeds the size limit")
        candidate = stage / "request.json"
        candidate.write_bytes(encoded)
        publish_file(candidate, args.request, encoded, REQUEST_LIMIT)
    return request


def attach(args):
    if args.output.suffix.lower() != ".ps1":
        raise ValueError("output must have a .ps1 extension")
    request, expected_data = read_request(args.request)
    if request["filename"] != args.source.name:
        raise ValueError("source filename differs from the signing request")
    source, encoding = read_source(args.source, request["source_sha256"])
    signature = read_file(args.signature, SIGNATURE_LIMIT, "signature")
    certificate = read_file(args.certificate, SIGNATURE_LIMIT, "publisher certificate")
    if certificate[0] != 0x30:
        raise ValueError("publisher certificate must be binary DER")
    publisher_digest = sha256(certificate)

    with tempfile.TemporaryDirectory(dir=args.output.parent) as scratch:
        stage = Path(scratch).resolve()
        if extract_data(args.osslsigncode, stage, source) != expected_data:
            raise ValueError("extracted signing data differs from the request")
        detached = stage / "signature.der"
        detached.write_bytes(signature)
        candidate = stage / "signed.ps1"
        run_tool(
            [str(args.osslsigncode), "attach-signature", "-h", "sha256", "-sigin",
             str(detached), "-in", str(stage / "source.ps1"), "-out", str(candidate)],
            "Authenticode signature attachment", cwd=stage,
        )
        expected = source + append_block(signature, encoding)
        signed = read_file(candidate, len(expected), "signed file")
        if signed != expected:
            raise ValueError("attachment altered source bytes or added an unexpected signature block")
        verify_windows(candidate, publisher_digest)
        publish_file(candidate, args.output, signed, len(expected))
    return {
        "workspace_id": request["workspace_id"], "project_id": request["project_id"],
        "issue_id": request["issue_id"], "filename": args.output.name,
        "source_sha256": request["source_sha256"], "sip_sha256": request["sip_sha256"],
        "signed_sha256": sha256(signed), "certificate_sha256": publisher_digest,
        "bytes": len(signed),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--osslsigncode", type=Path, default=INSTALL_ROOT / "bin/osslsigncode.exe")
    subcommands = parser.add_subparsers(dest="action", required=True)
    prep = subcommands.add_parser("prepare")
    prep.add_argument("--project", required=True)
    prep.add_argument("--issue", required=True)
    prep.add_argument("--source", type=Path, required=True)
    prep.add_argument("--expected-sha256", required=True)
    prep.add_argument("--request", type=Path, required=True)

    apply = subcommands.add_parser("attach")
    apply.add_argument("--source", type=Path, required=True)
    apply.add_argument("--request", type=Path, required=True)
    apply.add_argument("--signature", type=Path, required=True)
    apply.add_argument("--certificate", type=Path, default=INSTALL_ROOT / "publisher.cer")
    apply.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.osslsigncode.is_absolute():
        parser.error("--osslsigncode must be an absolute path to the installed tool")
    try:
        result = prepare(args) if args.action == "prepare" else attach(args)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        message = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"{args.action}: {message}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
