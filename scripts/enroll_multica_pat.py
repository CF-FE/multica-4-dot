#!/usr/bin/env python3
"""Enroll or rotate a Multica PAT on Vultr, after verifying its native account."""

import argparse
from contextlib import closing
import getpass
from http.client import HTTPConnection, HTTPSConnection, HTTPException
from ipaddress import ip_address, ip_network
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit
from uuid import UUID


DIRECTORY = Path("/etc/multica-backend")
PRIVATE_NETWORKS = tuple(map(ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


def verified_account(target, token):
    origin = urlsplit(target["origin"])
    if origin.username or origin.password or not origin.hostname or origin.path not in ("", "/") or origin.query or origin.fragment:
        raise ValueError("Invalid configured API origin.")
    if origin.scheme == "https":
        transport = HTTPSConnection
    elif origin.scheme == "http" and target.get("allow_private_http") is True and any(
        ip_address(origin.hostname) in network for network in PRIVATE_NETWORKS
    ):
        transport = HTTPConnection
    else:
        raise ValueError("Expected HTTPS or the enrolled private overlay origin.")
    if not token.startswith("mul_") or not token.isascii() or not all(
        c.isalnum() or c in "_-" for c in token
    ):
        raise ValueError("Expected a Multica personal access token.")
    with closing(transport(origin.hostname, origin.port, timeout=10)) as conn:
        conn.request("GET", "/api/me", headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
        with conn.getresponse() as response:
            if response.status != 200:
                raise ValueError(f"Multica identity check returned HTTP {response.status}.")
            data = response.read(65537)
    if len(data) > 65536:
        raise ValueError("Multica identity response exceeded its bound.")
    identity = json.loads(data)["id"]
    if str(UUID(identity)) != str(UUID(target["expected_user_id"])):
        raise ValueError("Token belongs to a different Multica account.")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--replace", action="store_true", help="replace a previously enrolled PAT")
    options.add_argument("--check", action="store_true", help="verify the stored PAT without printing it")
    parser.add_argument("--instance", default="tencent", help="enrolled instance in the service configuration")
    args = parser.parse_args()
    if os.geteuid() != 0 or DIRECTORY.is_symlink() or DIRECTORY.stat().st_uid != 0 or DIRECTORY.stat().st_mode & 0o077:
        parser.exit(1, "Use the root-owned private configuration directory.\n")
    config = DIRECTORY / "config.json"
    if config.exists():
        target = json.loads(config.read_text())["instances"][args.instance]
        credential = target.get("pat_credential")
        if not credential or Path(credential).name != credential or credential in {".", ".."}:
            parser.exit(1, "This instance does not use a named systemd credential.\n")
    elif args.instance == "tencent":
        target = json.loads((DIRECTORY / "pat-target.json").read_text())
        credential = "multica-pat"
    else:
        parser.exit(1, "Enroll this instance in config.json first.\n")
    path = DIRECTORY / credential
    if path.is_symlink():
        parser.exit(1, "Refusing a credential symlink.\n")
    if args.check:
        if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            parser.exit(1, "Invalid credential file permissions.\n")
        verified_account(target, path.read_text().strip())
        print("Stored PAT verified against the enrolled Multica account.")
        return
    if path.exists() and not args.replace:
        parser.exit(1, "Credential already exists. Use --replace to rotate.\n")
    if not sys.stdin.isatty():
        parser.exit(1, "A private interactive terminal is required. Use ssh -t.\n")
    token = getpass.getpass("Multica PAT (input hidden): ").strip()
    verified_account(target, token)
    with tempfile.NamedTemporaryFile(mode="w", dir=DIRECTORY, delete=False) as dest:
        staged = Path(dest.name)
        try:
            dest.write(token + "\n")
            dest.flush()
            os.fsync(dest.fileno())
            if args.replace:
                os.replace(staged, path)
            else:
                os.link(staged, path)
        finally:
            staged.unlink(missing_ok=True)
    print("PAT saved with mode 0600 and verified. Restart the active multica-backend.service to load it.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, HTTPException, ValueError, KeyError) as exc:
        # Never render remote JSON, request headers, or a credential in a traceback.
        if type(exc) is ValueError and exc.args and str(exc).startswith(("Token belongs", "Multica identity check", "Expected a Multica")):
            sys.exit(str(exc))
        sys.exit(f"Credential enrollment failed ({type(exc).__name__}).")
