"""OAuth client and stdio MCP proxy shared by assigned win-work DSH agents."""

import argparse
import asyncio
import ctypes
import errno
import json
import os
import sys
import tempfile
from contextlib import AsyncExitStack, aclosing, asynccontextmanager
from ctypes import wintypes
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastmcp import Client
from fastmcp.client.auth import OAuth
from fastmcp.server import create_proxy
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.stores.filetree.store import (
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

RESOURCE = "https://unbalance-presoak-pledge.ngrok-free.dev/decision-service/mcp"
CALLBACK_PORT = 49328
STORAGE = Path.home() / ".dsh" / "multica-oauth" / "decision-service"


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.c_void_p)]


def windows_protect(value: bytes, *, decrypt: bool = False) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    operation.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source = ctypes.create_string_buffer(value)
    input_blob = DataBlob(len(value), ctypes.cast(source, ctypes.c_void_p))
    result_blob = DataBlob()
    if not operation(ctypes.byref(input_blob), None, None, None, None, 1, ctypes.byref(result_blob)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result_blob.data, result_blob.size)
    finally:
        kernel32.LocalFree(result_blob.data)


def make_storage(*, login: bool) -> FernetEncryptionWrapper:
    key_path = STORAGE / "oauth-key.dpapi"
    if login and not key_path.exists():
        STORAGE.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=STORAGE, delete=False) as temporary:
            temporary.write(windows_protect(Fernet.generate_key()))
            temporary_path = Path(temporary.name)
        try:
            # Windows rename rejects a destination created by another login.
            temporary_path.rename(key_path)
        except FileExistsError:
            pass
        finally:
            temporary_path.unlink(missing_ok=True)

    key = windows_protect(key_path.read_bytes(), decrypt=True)
    storage_dir = STORAGE / "credentials"
    return FernetEncryptionWrapper(
        key_value=FileTreeStore(
            data_directory=storage_dir,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(storage_dir),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(storage_dir),
        ),
        fernet=Fernet(key),
    )


@asynccontextmanager
async def refresh_lock():
    import msvcrt

    deadline = asyncio.get_running_loop().time() + 55
    with (STORAGE / "refresh.lock").open("a+b") as lock_file:
        while True:
            lock_file.seek(0)
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno != errno.EACCES or asyncio.get_running_loop().time() >= deadline:
                    raise
                await asyncio.sleep(0.1)
        try:
            yield
        finally:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


class DecisionOAuth(OAuth):
    def __init__(self, *, login: bool):
        self.interactive_login = login
        super().__init__(
            mcp_url=RESOURCE,
            client_name="Multica DSH Decision Service",
            token_storage=make_storage(login=login),
            callback_port=CALLBACK_PORT,
            callback_host="127.0.0.1",
            callback_timeout=900,
        )

    async def _refresh_token(self):
        request = await super()._refresh_token()
        # A fresh process restores tokens without issuer metadata. Use the published
        # token endpoint under the same prefix as the decision service resource.
        if self.context.oauth_metadata is None:
            issuer_path = urlsplit(RESOURCE).path.removesuffix("/mcp")
            request.url = request.url.copy_with(path=issuer_path + "/token")
        return request

    async def _auth_flow(self, request):
        # MCP 2.3.0 yields a refresh request before the original resource request.
        # Close the first flow before waiting so it releases its SDK-local lock.
        async with AsyncExitStack() as flows:
            flow = await flows.enter_async_context(aclosing(super()._auth_flow(request)))
            try:
                outgoing = await anext(flow)
                if outgoing is not request:
                    await flow.aclose()
                    guard = await flows.enter_async_context(AsyncExitStack())
                    await guard.enter_async_context(refresh_lock())
                    async with self.context.lock:
                        await self._initialize()

                    flow = await flows.enter_async_context(aclosing(super()._auth_flow(request)))
                    outgoing = await anext(flow)
                    while outgoing is not request:
                        outgoing = await flow.asend((yield outgoing))
                    await guard.aclose()

                while True:
                    outgoing = await flow.asend((yield outgoing))
            except StopAsyncIteration:
                return

    async def redirect_handler(self, authorization_url: str) -> None:
        if not self.interactive_login:
            raise RuntimeError("Decision Service requires the shared win-work DSH login.")
        url = urlsplit(authorization_url)
        callback = parse_qs(url.query).get("redirect_uri")
        if (
            url.scheme != "https"
            or url.netloc != urlsplit(RESOURCE).netloc
            or url.path != "/decision-service/authorize"
            or callback != [f"http://127.0.0.1:{CALLBACK_PORT}/callback"]
        ):
            raise RuntimeError("Unexpected Decision Service OAuth authorization endpoint.")
        print("DECISION_OAUTH_URL=" + authorization_url, flush=True)


def make_client(*, login: bool) -> Client:
    return Client(
        RESOURCE,
        auth=DecisionOAuth(login=login),
        mode="legacy",
        timeout=910 if login else 55,
        init_timeout=910 if login else 55,
    )


async def authorize() -> None:
    async with make_client(login=True) as client:
        tools = {tool.name for tool in await client.list_tools()}
        if "get_decision" not in tools:
            raise RuntimeError("Decision Service did not expose get_decision.")
    print(json.dumps({"status": "authorized", "get_decision": True}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("login", "stdio"))
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This adapter requires the Windows DSH host.")
    if args.mode == "login":
        asyncio.run(authorize())
    else:
        proxy = create_proxy(make_client(login=False), name="Decision Service")
        proxy.run(transport="stdio", show_banner=False, log_level="ERROR")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Response URLs or payloads in SDK exceptions may contain OAuth credentials.
        print(f"Decision Service OAuth failed ({type(exc).__name__}).", file=sys.stderr)
        if isinstance(exc, FileNotFoundError):
            print("Run the shared win-work DSH login first.", file=sys.stderr)
        sys.exit(1)
