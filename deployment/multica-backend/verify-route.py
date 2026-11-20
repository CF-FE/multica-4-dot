#!/usr/bin/env python3
"""Check Multica MCP routing and discovery without signing in or calling tools."""

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PREFIX = "/multica-backend"
ISSUER_METADATA = "/.well-known/oauth-authorization-server" + PREFIX
RESOURCE_METADATA = "/.well-known/oauth-protected-resource" + PREFIX + "/mcp"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def verify(label, origin, public_base, *, public):
    opener = build_opener(NoRedirect())

    def request(path, status, *, post=False):
        data = b"{}" if post else None
        headers = {"Accept": "application/json, text/event-stream"} if post else {}
        if post:
            headers["Content-Type"] = "application/json"
        try:
            response = opener.open(Request(origin + path, data=data, headers=headers), timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            if response.code != status:
                raise ValueError(f"{label} {path}: expected HTTP {status}, got {response.code}")
            header = response.headers.get("WWW-Authenticate", "")
            payload = json.loads(response.read(65536)) if not post else None
        return header, payload

    if not public:
        _, health = request("/health", 200)
        if health != {"status": "ok"}:
            raise ValueError("local /health: unexpected response")

    mcp_path = PREFIX + "/mcp" if public else "/mcp"
    header, _ = request(mcp_path, 401, post=True)
    public_origin = public_base.removesuffix(PREFIX)
    metadata_url = public_origin + RESOURCE_METADATA
    if not header.startswith("Bearer ") or f'resource_metadata="{metadata_url}"' not in header:
        raise ValueError(f"{label} {mcp_path}: incorrect OAuth challenge")

    _, resource = request(RESOURCE_METADATA, 200)
    if resource.get("resource") != public_base + "/mcp" or resource.get("authorization_servers") != [public_base]:
        raise ValueError(f"{label}: incorrect protected resource metadata")

    _, issuer = request(ISSUER_METADATA, 200)
    expected = {
        "issuer": public_base,
        "authorization_endpoint": public_base + "/authorize",
        "token_endpoint": public_base + "/token",
        "registration_endpoint": public_base + "/register",
    }
    if any(issuer.get(field) != value for field, value in expected.items()):
        raise ValueError(f"{label}: incorrect issuer or endpoint metadata")
    if "S256" not in issuer.get("code_challenge_methods_supported", []):
        raise ValueError(f"{label}: issuer does not advertise PKCE S256")
    print(f"PASS {label}: MCP 401, exact challenge, resource and issuer discovery, PKCE S256")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public_base", help="The configured HTTPS issuer, ending in /multica-backend")
    parser.add_argument("--local-only", action="store_true", help="Skip the public HTTPS probe")
    parser.add_argument("--local-port", type=int, default=8770, help="Loopback port, default 8770")
    args = parser.parse_args()
    base = args.public_base
    url = urlsplit(base)
    if (url.scheme != "https" or not url.hostname or url.username is not None or url.path != PREFIX
            or any(char.isspace() or char in "?#\\" for char in base)):
        parser.error("public_base must be an HTTPS origin followed by /multica-backend")
    try:
        verify("local", f"http://127.0.0.1:{args.local_port}", base, public=False)
        if not args.local_only:
            verify("public", base.removesuffix(PREFIX), base, public=True)
    except (ValueError, AttributeError, TypeError, URLError, TimeoutError) as exc:
        if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError):
            print(f"FAIL: {exc}", file=sys.stderr)
        else:
            print(f"FAIL: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
