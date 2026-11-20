import base64
import hashlib
import json
import re
import socket
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import uvicorn
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.jwt_issuer import JWTIssuer
from fastmcp.server.auth.oauth_proxy.upstream import AsyncOAuth2Client
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from starlette.testclient import TestClient

from multica_backend.auth import AuthError, Caller, GitHubOAuth
from multica_backend.multica_api import MulticaAPIError
from multica_backend.server import build_app, create_app

PUBLIC = "https://multica.example.invalid/multica-backend"
CALLBACK = "https://dot.example.invalid/callback"
METADATA = "/.well-known/oauth-protected-resource/multica-backend/mcp"
ISSUER_METADATA = "/.well-known/oauth-authorization-server/multica-backend"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
INITIALIZE = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "fixture", "version": "1"}}
TOOLS = [
    {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": {}},
        "readOnly": read_only,
    }
    for name, description, read_only in [
        ("get_issue", "Read an issue.", True),
        ("dispatch", "Dispatch an issue.", False),
    ]
]


class GatewayFixture:
    def __init__(self):
        self.calls = []

    def call(self, principal, name, arguments):
        self.calls.append((principal, name, arguments))
        return {"principal": principal, "action": name}


class LoopbackOAuth:
    public_host = "multica.example.invalid"
    public_origin = "https://multica.example.invalid"
    challenge = f'Bearer resource_metadata="{public_origin}{METADATA}"'
    routes = []

    async def authenticate(self, authorization):
        if authorization == "Bearer fixture-read":
            return Caller("github:1001", frozenset({"read"}))
        if authorization == "Bearer fixture-write":
            return Caller("github:1002", frozenset({"read", "write"}))
        raise AuthError(401, "unauthenticated")


def request(client, method, params=None, *, bearer=None, request_id=1, **headers):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if request_id is not None:
        body["id"] = request_id
    if bearer is not None:
        headers["Authorization"] = "Bearer " + bearer
    return client.post("/mcp", headers={**MCP_HEADERS, **headers}, json=body)


@contextmanager
def serve_loopback(app):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="error", lifespan="on"))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started and worker.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not server.started:
                raise RuntimeError("loopback MCP server did not start")
            with httpx.Client(base_url=f"http://127.0.0.1:{listener.getsockname()[1]}", trust_env=False) as client:
                yield client
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError("loopback MCP server did not stop")


class GatewayHttpTests(unittest.TestCase):
    def test_streamable_http_auth_discovery_and_read_write_scope(self):
        gateway = GatewayFixture()
        with serve_loopback(build_app(gateway, TOOLS, LoopbackOAuth())) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            missing = request(client, "initialize", INITIALIZE, **{"X-Principal": "github:1002"})
            self.assertEqual(missing.status_code, 401)
            self.assertIn(METADATA, missing.headers["www-authenticate"])
            init = request(client, "initialize", INITIALIZE, bearer="fixture-read")
            self.assertEqual(init.json()["result"]["protocolVersion"], "2025-11-25")
            self.assertEqual(request(client, "notifications/initialized", bearer="fixture-read",
                                     request_id=None).status_code, 202)
            visible = request(client, "tools/list", bearer="fixture-read").json()["result"]["tools"]
            self.assertEqual([tool["name"] for tool in visible], ["get_issue"])
            self.assertTrue(visible[0]["annotations"]["readOnlyHint"])
            visible = request(client, "tools/list", bearer="fixture-write").json()["result"]["tools"]
            self.assertEqual([tool["name"] for tool in visible], ["get_issue", "dispatch"])
            self.assertFalse(visible[1]["annotations"]["readOnlyHint"])
            denied = request(client, "tools/call", {"name": "dispatch", "arguments": {}},
                             bearer="fixture-read", **{"X-Principal": "github:1002"})
            outcome = denied.json()["result"]
            self.assertTrue(outcome["isError"])
            self.assertEqual(outcome["structuredContent"]["error"]["code"], "forbidden_scope")
            self.assertEqual(gateway.calls, [])
            for action, bearer, principal in [("get_issue", "fixture-read", "github:1001"),
                                               ("dispatch", "fixture-write", "github:1002")]:
                response = request(client, "tools/call", {"name": action, "arguments": {}}, bearer=bearer)
                result = response.json()["result"]
                self.assertFalse(result["isError"])
                self.assertEqual(result["structuredContent"], {"principal": principal, "action": action})
                self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
            self.assertEqual(gateway.calls, [
                ("github:1001", "get_issue", {}),
                ("github:1002", "dispatch", {}),
            ])
            no_sse = client.get("/mcp", headers={**MCP_HEADERS, "Authorization": "Bearer fixture-read"})
            self.assertEqual(no_sse.status_code, 405)

    def test_untrusted_host_origin_and_non_mcp_token_do_not_reach_gateway(self):
        gateway = GatewayFixture()
        with serve_loopback(build_app(gateway, TOOLS, LoopbackOAuth())) as client:
            self.assertEqual(request(client, "tools/list", Origin="https://wrong.invalid").status_code, 403)
            self.assertEqual(request(client, "tools/list", Host="wrong.invalid").status_code, 400)
            self.assertEqual(request(client, "tools/list", bearer="mul_synthetic").status_code, 401)
            self.assertEqual(gateway.calls, [])


def oauth_environment(directory):
    return {
        "MULTICA_MCP_PUBLIC_BASE_URL": PUBLIC,
        "MULTICA_MCP_GITHUB_CLIENT_ID": "synthetic-client-id",
        "MULTICA_MCP_GITHUB_CLIENT_SECRET": "synthetic-client-secret",
        "MULTICA_MCP_OAUTH_SIGNING_KEY": "test-signing-material-" * 3,
        "MULTICA_MCP_OAUTH_STATE_DIR": str(directory / "oauth"),
        "MULTICA_MCP_GITHUB_PRINCIPALS": '{"42":{"scopes":["read","write"]}}',
        "MULTICA_MCP_ALLOWED_REDIRECT_URIS": json.dumps([CALLBACK]),
    }


def register(client):
    payload = {
        "redirect_uris": [CALLBACK],
        "application_type": "web",
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": "read:user",
    }
    denied = client.post("/register", json={**payload, "redirect_uris": ["https://wrong.invalid/callback"]})
    assert denied.status_code == 400, denied.text
    response = client.post("/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["client_id"]


def exchange_details(client, client_id):
    verifier = "isolated_pkce_" + "A" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    authorize = client.get("/authorize", params={
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "scope": "read:user",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": PUBLIC + "/mcp",
        "state": "isolated-client-state",
    })
    assert authorize.is_redirect, authorize.text
    transaction = parse_qs(urlsplit(authorize.headers["location"]).query)["txn_id"][0]
    consent = client.get("/consent", params={"txn_id": transaction}).raise_for_status()
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', consent.text).group(1)
    approval = client.post("/consent", data={"txn_id": transaction, "csrf_token": csrf, "action": "approve"})
    assert approval.is_redirect, approval.text
    upstream = urlsplit(approval.headers["location"])
    assert upstream.hostname == "github.com"
    github_parameters = parse_qs(upstream.query)
    assert github_parameters["redirect_uri"] == [PUBLIC + "/auth/callback"]
    callback = client.get("/auth/callback", params={"state": github_parameters["state"][0], "code": "isolated-code"})
    assert callback.is_redirect, callback.text
    result = parse_qs(urlsplit(callback.headers["location"]).query)
    assert result["state"] == ["isolated-client-state"]
    return {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "code": result["code"][0],
        "code_verifier": verifier,
        "resource": PUBLIC + "/mcp",
    }


class OAuthTests(unittest.TestCase):
    def test_configuration_fails_closed(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "MULTICA_MCP_PUBLIC_BASE_URL"):
                create_app()
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", oauth_environment(Path(directory))):
            with patch.dict("os.environ", {"MULTICA_MCP_GITHUB_PRINCIPALS": '{"alias":{"scopes":["read"]}}'}):
                with self.assertRaisesRegex(ValueError, "numeric GitHub user IDs"):
                    GitHubOAuth.from_env()
            with patch.dict("os.environ", {"MULTICA_MCP_ALLOWED_REDIRECT_URIS": '["https://*.invalid/callback"]'}):
                with self.assertRaisesRegex(ValueError, "explicit HTTPS or loopback URLs"):
                    GitHubOAuth.from_env()

    def test_configured_gateway_output_keeps_upstream_and_oauth_failures_distinct(self):
        workspace_id = "12345678-0000-4000-8000-000000000000"
        project_id = "12345678-0000-4000-8000-000000000001"

        async def verify_fixture(_oauth, authorization):
            return await LoopbackOAuth().authenticate(authorization)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            registry = path / "instances.json"
            registry.write_text(json.dumps({"instances": {
                "fixture": {
                    "origin": "https://native.example.invalid",
                    "expected_user_id": "12345678-0000-4000-8000-000000000002",
                    "pat_env": "MULTICA_TEST_NATIVE_TOKEN",
                    "principals": ["github:1001"],
                    "workspaces": {workspace_id: {"coordinator_id": "12345678-0000-4000-8000-000000000003"}},
                },
            }}))
            config = {
                **oauth_environment(path),
                "MULTICA_MCP_CONFIG": str(registry),
                "MULTICA_MCP_STATE_DIR": str(path / "gateway"),
                "MULTICA_TEST_NATIVE_TOKEN": "mul_fixture",
            }
            with (patch.dict("os.environ", config),
                  patch.object(GitHubOAuth, "authenticate", verify_fixture),
                  patch("multica_backend.multica_api.MulticaAPI.get_project",
                        side_effect=MulticaAPIError("project", "unauthenticated", http_status=401))):
                with TestClient(create_app(), base_url="https://multica.example.invalid") as client:
                    response = request(client, "tools/call", {"name": "list_instances", "arguments": {}},
                                       bearer="fixture-read")
                    self.assertEqual(response.json()["result"]["structuredContent"],
                                     {"instances": [{"instance_id": "fixture", "workspace_ids": [workspace_id]}]})
                    invalid = request(client, "tools/call", {"name": "get_project", "arguments": {}},
                                      bearer="fixture-read")
                    self.assertEqual(invalid.json()["result"]["structuredContent"]["error"]["code"],
                                     "invalid_arguments")
                    failed = request(client, "tools/call", {"name": "get_project", "arguments": {
                        "instance_id": "fixture", "workspace_id": workspace_id, "project_id": project_id,
                    }}, bearer="fixture-read")
                    self.assertEqual(failed.status_code, 200)
                    self.assertNotIn("www-authenticate", failed.headers)
                    error = failed.json()["result"]["structuredContent"]["error"]
                    self.assertEqual(error["code"], "unauthenticated")
                    self.assertEqual(error["http_status"], 401)

    def test_oauth_callback_audience_subject_and_encrypted_restart(self):
        github_id = "42"

        async def github_exchange(_client, **parameters):
            self.assertEqual(parameters["code"], "isolated-code")
            return {"access_token": "synthetic-upstream-token", "token_type": "Bearer", "scope": "read:user"}

        async def github_identity(_verifier, token):
            self.assertEqual(token, "synthetic-upstream-token")
            return AccessToken(
                token=token, client_id=github_id, scopes=["read:user"], subject=github_id,
                claims={"login": "renamed-account"},
            )

        gateway = GatewayFixture()
        with tempfile.TemporaryDirectory() as directory:
            config = oauth_environment(Path(directory))
            with (patch.dict("os.environ", config),
                  patch.object(AsyncOAuth2Client, "fetch_token", github_exchange),
                  patch.object(GitHubTokenVerifier, "verify_token", github_identity)):
                oauth = GitHubOAuth.from_env()
                with TestClient(build_app(gateway, TOOLS, oauth), base_url=oauth.public_origin,
                                follow_redirects=False) as client:
                    self.assertEqual(request(client, "tools/list").status_code, 401)
                    metadata = client.get(METADATA).raise_for_status().json()
                    self.assertEqual(metadata["resource"], PUBLIC + "/mcp")
                    self.assertEqual(metadata["authorization_servers"], [PUBLIC])
                    discovery = client.get(ISSUER_METADATA).raise_for_status().json()
                    self.assertEqual(discovery["issuer"], PUBLIC)
                    self.assertEqual(discovery["registration_endpoint"], PUBLIC + "/register")
                    self.assertIn("S256", discovery["code_challenge_methods_supported"])
                    client_id = register(client)
                    exchange = exchange_details(client, client_id)
                    token = client.post("/token", data=exchange).raise_for_status().json()["access_token"]
                    self.assertNotIn("synthetic-upstream-token", token)
                    rejected = request(client, "tools/list", bearer="synthetic-upstream-token")
                    self.assertEqual(rejected.status_code, 401)
                    issuer = oauth.provider.jwt_issuer
                    claims = issuer.verify_token(token)
                    self.assertEqual(claims["aud"], PUBLIC + "/mcp")
                    for wrong_iss, wrong_aud in [
                        (issuer.issuer, "https://multica.example.invalid/mailbox/mcp"),
                        ("https://multica.example.invalid/mailbox", issuer.audience),
                    ]:
                        foreign = JWTIssuer(wrong_iss, wrong_aud, issuer._signing_key).issue_access_token(
                            client_id, ["read:user"], claims["jti"],
                        )
                        self.assertEqual(request(client, "tools/list", bearer=foreign).status_code, 401)
                    expired = issuer.issue_access_token(client_id, ["read:user"], claims["jti"], expires_in=-180)
                    self.assertEqual(request(client, "tools/list", bearer=expired).status_code, 401)
                    github_id = "999"
                    self.assertEqual(request(client, "tools/list", bearer=token).status_code, 403)
                    self.assertEqual(gateway.calls, [])
                    github_id = "42"

                state_files = [file for file in Path(config["MULTICA_MCP_OAUTH_STATE_DIR"]).rglob("*") if file.is_file()]
                self.assertTrue(state_files)
                self.assertTrue(all(b"synthetic-upstream-token" not in file.read_bytes() for file in state_files))
                reopened = GitHubOAuth.from_env()
                with TestClient(build_app(gateway, TOOLS, reopened), base_url=reopened.public_origin) as client:
                    dispatched = request(client, "tools/call", {"name": "dispatch", "arguments": {}}, bearer=token)
                    self.assertEqual(dispatched.json()["result"]["structuredContent"]["principal"], "github:42")
                    self.assertEqual(gateway.calls, [("github:42", "dispatch", {})])


if __name__ == "__main__":
    unittest.main()
