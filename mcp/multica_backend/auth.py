"""GitHub-backed OAuth for the Multica MCP resource."""

import asyncio
import json
import logging
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fastmcp.server.auth.providers.github import GitHubProvider
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from mcp.server.auth.routes import build_resource_metadata_url
from pydantic import AnyHttpUrl

logger = logging.getLogger(__name__)
GITHUB_SCOPE = "read:user"
PUBLIC_PREFIX = "/multica-backend"
OAUTH_STORAGE_BYTES = 8 * 1024 * 1024
OAUTH_STORAGE_FILES = 512
ALLOWED_SCOPES = frozenset({"read", "write"})


@dataclass(frozen=True)
class Caller:
    principal: str
    scopes: frozenset[str]


class AuthError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _json_setting(name: str):
    try:
        return json.loads(_required(name))
    except json.JSONDecodeError:
        raise ValueError(f"{name} must contain valid JSON") from None


def _oauth_url(value: str, *, allow_loopback: bool = False):
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        return None
    if not url.hostname or url.username is not None or url.password is not None:
        return None
    if any(ord(character) <= 32 or character in "\\*?#" for character in value):
        return None
    if "[" in url.path or "]" in url.path:
        return None
    if url.scheme == "https" or (
        allow_loopback and url.scheme == "http" and url.hostname in {"127.0.0.1", "::1", "localhost"} and port
    ):
        return url
    return None


class _OAuthStoreFull(RuntimeError):
    pass


class _BoundedOAuthStore(FileTreeStore):
    """Bound the single worker's encrypted OAuth state.

    Adapted from decision-service's BoundedOAuthFileTreeStore.
    """

    def __init__(self, directory: Path):
        if not directory.is_absolute() or directory.is_symlink():
            raise ValueError("MULTICA_MCP_OAUTH_STATE_DIR must name an absolute private directory")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_mode & 0o077:
            raise ValueError("MULTICA_MCP_OAUTH_STATE_DIR must have owner-only permissions")
        self.directory = directory.resolve()
        self.write_lock = asyncio.Lock()
        super().__init__(
            data_directory=self.directory,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(self.directory),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(self.directory),
        )

    def _usage(self) -> tuple[int, int]:
        files = allocated = 0
        pending = [self.directory]
        while pending:
            path = pending.pop()
            info = path.lstat()
            allocated += max(info.st_size, info.st_blocks * 512)
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    pending.extend(Path(entry.path) for entry in entries)
            elif stat.S_ISREG(info.st_mode):
                files += 1
            else:
                raise _OAuthStoreFull("OAuth storage contains an unsupported entry")
        return files, allocated

    async def _admit(self, snapshots) -> None:
        # Reserve space for both ciphertext and metadata written by FileTreeStore.
        reserve = sum(2 * len(json.dumps(value, ensure_ascii=True)) + 16384 for value in snapshots)
        files, allocated = await asyncio.to_thread(self._usage)
        if files + 2 * len(snapshots) > OAUTH_STORAGE_FILES or allocated + reserve > OAUTH_STORAGE_BYTES:
            raise _OAuthStoreFull("OAuth storage capacity reached")

    async def put(self, key, value, *, collection=None, ttl=None):
        snapshot = dict(value)
        async with self.write_lock:
            await self._admit([snapshot])
            await super().put(key, snapshot, collection=collection, ttl=ttl)

    async def put_many(self, keys, values, *, collection=None, ttl=None):
        snapshots = [dict(value) for value in values]
        async with self.write_lock:
            await self._admit(snapshots)
            await super().put_many(keys, snapshots, collection=collection, ttl=ttl)


class _SafeExchangeClient:
    def __init__(self, upstream):
        self.upstream = upstream

    def __getattr__(self, name):
        return getattr(self.upstream, name)

    async def fetch_token(self, **parameters):
        try:
            return await self.upstream.fetch_token(**parameters)
        except Exception as exc:
            # The provider displays this exception in the OAuth callback response.
            logger.warning("GitHub OAuth exchange failed (%s)", type(exc).__name__)
            raise RuntimeError("GitHub did not complete the token exchange.") from None


class _MulticaGitHubProvider(GitHubProvider):
    def _create_upstream_oauth_client(self):
        return _SafeExchangeClient(super()._create_upstream_oauth_client())


class GitHubOAuth:
    def __init__(self, *, public_url, client_id, client_secret, signing_key, state_dir, principals, redirects):
        self.principals = principals
        self.public_origin = f"{public_url.scheme}://{public_url.netloc}"
        self.public_host = public_url.hostname
        base_url = public_url.geturl()
        self.resource_url = base_url + "/mcp"
        storage = FernetEncryptionWrapper(
            _BoundedOAuthStore(state_dir), source_material=signing_key, salt="multica-backend/oauth-state"
        )
        self.provider = _MulticaGitHubProvider(
            client_id=client_id,
            client_secret=client_secret,
            base_url=base_url,
            issuer_url=base_url,
            resource_base_url=base_url,
            redirect_path="/auth/callback",
            required_scopes=[GITHUB_SCOPE],
            jwt_signing_key=signing_key,
            client_storage=storage,
            allowed_client_redirect_uris=redirects,
            require_authorization_consent=True,
            enable_cimd=False,
            forward_resource=False,
        )
        metadata = build_resource_metadata_url(AnyHttpUrl(self.resource_url))
        self.challenge = f'Bearer resource_metadata="{metadata}", scope="{GITHUB_SCOPE}"'
        discovery_paths = {
            "/.well-known/oauth-authorization-server" + PUBLIC_PREFIX,
            "/.well-known/openid-configuration" + PUBLIC_PREFIX,
            metadata.path,
        }
        self.routes = [
            route for route in self.provider.get_routes("/mcp") if not route.path.startswith("/.well-known/")
        ] + [
            route for route in self.provider.get_well_known_routes("/mcp") if route.path in discovery_paths
        ]

    @classmethod
    def from_env(cls):
        public_url = _oauth_url(_required("MULTICA_MCP_PUBLIC_BASE_URL").rstrip("/"))
        if public_url is None or public_url.path != PUBLIC_PREFIX:
            raise ValueError("MULTICA_MCP_PUBLIC_BASE_URL must be an HTTPS URL ending in /multica-backend")
        client_id = _required("MULTICA_MCP_GITHUB_CLIENT_ID")
        client_secret = _required("MULTICA_MCP_GITHUB_CLIENT_SECRET")
        signing_key = _required("MULTICA_MCP_OAUTH_SIGNING_KEY")
        if len(signing_key) < 43 or signing_key == client_secret:
            raise ValueError("MULTICA_MCP_OAUTH_SIGNING_KEY must be an independent high-entropy secret")
        state_dir = Path(_required("MULTICA_MCP_OAUTH_STATE_DIR"))

        raw_principals = _json_setting("MULTICA_MCP_GITHUB_PRINCIPALS")
        if not isinstance(raw_principals, dict) or not raw_principals:
            raise ValueError("MULTICA_MCP_GITHUB_PRINCIPALS must be a nonempty object")
        principals = {}
        for github_id, policy in raw_principals.items():
            if not re.fullmatch(r"[1-9][0-9]{0,29}", github_id) or not isinstance(policy, dict):
                raise ValueError("OAuth policy keys must be numeric GitHub user IDs")
            scopes = policy.get("scopes")
            if (
                set(policy) != {"scopes"}
                or not isinstance(scopes, list)
                or not scopes
                or any(not isinstance(scope, str) or scope not in ALLOWED_SCOPES for scope in scopes)
            ):
                raise ValueError("OAuth policies require read/write scopes")
            principals[github_id] = Caller(f"github:{github_id}", frozenset(scopes))

        redirects = _json_setting("MULTICA_MCP_ALLOWED_REDIRECT_URIS")
        if (
            not isinstance(redirects, list)
            or not redirects
            or any(not isinstance(uri, str) or not _oauth_url(uri, allow_loopback=True) for uri in redirects)
        ):
            raise ValueError("MULTICA_MCP_ALLOWED_REDIRECT_URIS requires explicit HTTPS or loopback URLs")
        return cls(
            public_url=public_url,
            client_id=client_id,
            client_secret=client_secret,
            signing_key=signing_key,
            state_dir=state_dir,
            principals=principals,
            redirects=redirects,
        )

    async def authenticate(self, authorization: str | None) -> Caller:
        scheme, _, bearer = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not bearer or len(bearer) > 8192 or any(c.isspace() for c in bearer):
            raise AuthError(401, "unauthenticated")
        # FastMCP checks signature, issuer, audience, expiry and token use before
        # resolving the GitHub token. The upstream verifier supplies the user ID.
        token = await self.provider.verify_token(bearer)
        if token is None or GITHUB_SCOPE not in token.scopes:
            raise AuthError(401, "unauthenticated")
        caller = self.principals.get(token.subject)
        if caller is None:
            raise AuthError(403, "forbidden_scope")
        return caller
