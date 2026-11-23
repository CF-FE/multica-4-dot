"""Operator entry point: sign one reviewed win-work PowerShell file over existing SSH."""

import argparse
import base64
import codecs
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import uuid

from reviewed_sip import verify_reviewed_sip
from workspace_sign import append_block


WORKSPACE = "e25be43b-82b6-419d-9085-bb5c5700b1af"
SIGNER = "/usr/local/lib/multica-workspace-signing/sign_release.py"
PUBLIC_CERT = "/var/lib/multica-workspace-signing/publisher.cer"
WINDOWS_HOME = r"C:\Program Files\Multica Workspace Signing"
HEX = re.compile(r"[0-9a-f]{64}")


def run(argv, *, data=None, timeout=45):
    result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        # Remote PowerShell can add CLIXML. Keep diagnostics bounded.
        raise RuntimeError(message[:1200] or f"{argv[0]} exited with {result.returncode}")
    return result.stdout


def ps_string(value):
    return "'" + str(value).replace("'", "''") + "'"


def windows(host, script):
    preamble = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
    payload = base64.b64encode((preamble + script).encode("utf-16le")).decode()
    return run(["ssh", "-T", "-o", "BatchMode=yes", host, "powershell.exe", "-NoLogo",
                "-NoProfile", "-NonInteractive", "-EncodedCommand", payload])


def sign(args):
    token = os.environ.get("MULTICA_TOKEN", "")
    if not token or not token.isascii() or any(ch.isspace() for ch in token):
        raise ValueError("set MULTICA_TOKEN for an operator who can read the named project and Issue")
    for host in (args.win_host, args.sign_host):
        if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.@-]*", host):
            raise ValueError("invalid configured SSH destination")
    for path in (args.source, args.output):
        w = PureWindowsPath(path)
        if (not w.is_absolute() or not re.fullmatch("[A-Za-z]:", w.drive)
                or w.suffix.lower() != ".ps1" or ".." in w.parts
                or any(ord(ch) < 32 for ch in path) or ":" in path[2:]):
            raise ValueError("use an absolute local-drive .ps1 path")
    if PureWindowsPath(args.source) == PureWindowsPath(args.output):
        raise ValueError("choose a separate signed destination; the reviewed input is preserved")
    if not HEX.fullmatch(args.approved_sha256):
        raise ValueError("pass the independently reviewed unsigned SHA-256 in lowercase")
    with args.reviewed_file.open("rb") as original:
        reviewed = original.read(1024 * 1024 + 1)
    if len(reviewed) > 1024 * 1024 or hashlib.sha256(reviewed).hexdigest() != args.approved_sha256:
        raise ValueError("the operator's independently reviewed copy differs from the approved SHA-256")

    ssh = ["ssh", "-T", "-o", "BatchMode=yes", args.sign_host]
    pin = run([*ssh, "sudo", "-n", "sha256sum", PUBLIC_CERT]).decode().split()[0]
    if not HEX.fullmatch(pin):
        raise ValueError("could not read enrolled publisher identity")

    home = ps_string(WINDOWS_HOME)
    ident = str(uuid.uuid4())
    # Both phase invocations use a unique operator scratch directory on win-work.
    env = f"""
$homeDir={home}
$py=([IO.File]::ReadAllText((Join-Path $homeDir 'client.json')) | ConvertFrom-Json).python
$client=Join-Path $homeDir 'workspace_sign.py'
$cert=Join-Path $homeDir 'publisher.cer'
if((Get-FileHash -Algorithm SHA256 -LiteralPath $cert).Hash -ne '{pin}'){{throw 'Publisher fingerprint mismatch'}}
$scratch=Join-Path ([IO.Path]::GetTempPath()) 'multica-signing-{ident}'
$req=Join-Path $scratch 'request.json'
$sig=Join-Path $scratch 'signature.der'
"""
    try:
        # Construct the SIP from the file selected by the operator; never take an
        # Agent-supplied pair of hashes as evidence of which bytes were reviewed.
        raw = windows(args.win_host, env + f"""
$null=New-Item -ItemType Directory -Path $scratch -ErrorAction Stop
& $py -I -B $client prepare --project '{args.project}' --issue '{args.issue}' --source {ps_string(args.source)} --expected-sha256 '{args.approved_sha256}' --request $req | Out-Null
if($LASTEXITCODE -ne 0){{throw 'Preparation failed; verify the approved bytes and input format'}}
[Console]::Write([IO.File]::ReadAllText($req))
""")
        packet = json.loads(raw)
        if ((packet["workspace_id"], packet["project_id"], packet["issue_id"],
             packet["source_sha256"], packet["filename"]) !=
                (WORKSPACE, str(args.project), str(args.issue), args.approved_sha256,
                 PureWindowsPath(args.source).name)):
            raise ValueError("request does not match the reviewed source or issue")
        der = base64.b64decode(packet["sip_der_base64"], validate=True)
        sip_sha = hashlib.sha256(der).hexdigest()
        if sip_sha != packet["sip_sha256"] or len(der) != 150:
            raise ValueError("unexpected Authenticode indirect data")
        verify_reviewed_sip(reviewed, args.approved_sha256, der)
        signed = run([*ssh, "sudo", "-n", "/usr/bin/python3", "-I", SIGNER,
                      "--project", str(args.project), "--issue", str(args.issue),
                      "--source-sha256", args.approved_sha256, "--expected-sip-sha256",
                      sip_sha, "--token-stdin"], data=token.encode() + b"\n" + der)
        if not signed.startswith(b"0") or not 256 <= len(signed) <= 65536:
            raise ValueError("unexpected signature response; reconcile the original release")

        # Transfer the public signature without pushing executable source to the signer.
        # Keep each encoded command below Windows OpenSSH command line limits.
        b64 = base64.b64encode(signed).decode()
        for start in range(0, len(b64), 1400):
            chunk = b64[start:start + 1400]
            windows(args.win_host, env + f"""
$part=[Convert]::FromBase64String('{chunk}')
$mode={'[IO.FileMode]::CreateNew' if start == 0 else '[IO.FileMode]::Append'}
$s=[IO.File]::Open($sig,$mode,[IO.FileAccess]::Write,[IO.FileShare]::None)
try{{$s.Write($part,0,$part.Length)}}finally{{$s.Dispose()}}
""")
        raw = windows(args.win_host, env + f"""
if((Get-FileHash -Algorithm SHA256 -LiteralPath $sig).Hash -ne '{hashlib.sha256(signed).hexdigest()}'){{throw 'Signature transfer mismatch'}}
& $py -I -B $client attach --source {ps_string(args.source)} --request $req --signature $sig --certificate $cert --output {ps_string(args.output)}
if($LASTEXITCODE -ne 0){{throw 'Signed artifact verification or publication failed'}}
""")
        receipt = json.loads(raw)
        encoding = "utf-16-le" if reviewed.startswith(codecs.BOM_UTF16_LE) else "utf-8"
        signed_bytes = reviewed + append_block(signed, encoding)
        expected = {
            "workspace_id": WORKSPACE, "project_id": str(args.project), "issue_id": str(args.issue),
            "filename": PureWindowsPath(args.output).name, "source_sha256": args.approved_sha256,
            "sip_sha256": sip_sha, "signed_sha256": hashlib.sha256(signed_bytes).hexdigest(),
            "certificate_sha256": pin, "bytes": len(signed_bytes),
        }
        if receipt != expected:
            raise ValueError("Windows delivery receipt differs from the approved release")
        return receipt
    finally:
        # Only three known, invocation-specific paths; never remove project files.
        first_error = sys.exc_info()[0] is not None
        try:
            windows(args.win_host, env + """
foreach($f in @($req,$sig)){if([IO.File]::Exists($f)){[IO.File]::Delete($f)}}
if([IO.Directory]::Exists($scratch)){[IO.Directory]::Delete($scratch,$false)}
""")
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            if not first_error:
                raise
            print(f"Check the operator scratch directory multica-signing-{ident} on win-work.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=uuid.UUID)
    parser.add_argument("--issue", required=True, type=uuid.UUID)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--approved-sha256", required=True)
    parser.add_argument("--reviewed-file", type=Path, required=True,
                        help="independently reviewed original bytes on the operator workstation")
    parser.add_argument("--win-host", default="admin@192.168.100.35")
    parser.add_argument("--sign-host", default="tencent")
    try:
        result = sign(parser.parse_args())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Workspace signing: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
