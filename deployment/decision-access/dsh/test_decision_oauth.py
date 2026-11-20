"""Offline regression for shared OAuth refresh using two Windows processes."""

import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import aclosing
from pathlib import Path
from urllib.parse import parse_qs

if os.name == "nt":
    import httpx2
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

    spec = importlib.util.spec_from_file_location(
        "decision_oauth", Path(__file__).with_name("decision_oauth.py")
    )
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    adapter.RESOURCE = "https://oauth.test/decision-service/mcp"


async def seed_storage(folder: Path) -> None:
    adapter.STORAGE = folder
    provider = adapter.DecisionOAuth(login=True)
    await provider.token_storage_adapter.set_client_info(
        OAuthClientInformationFull(client_id="offline-client")
    )
    await provider.token_storage_adapter.set_tokens(
        OAuthToken(access_token="expired-access", refresh_token="old-refresh", expires_in=1)
    )


async def wait_for_file(path: Path) -> None:
    async with asyncio.timeout(12):
        while not path.exists():
            await asyncio.sleep(0.05)


async def exercise_client(folder: Path, client: str, other: str) -> None:
    adapter.STORAGE = folder
    provider = adapter.DecisionOAuth(login=False)
    await provider._initialize()
    (folder / f"ready-{client}").touch()
    await wait_for_file(folder / "start")
    assert not provider.context.is_token_valid()

    request = httpx2.Request("POST", adapter.RESOURCE)
    async with aclosing(provider.async_auth_flow(request)) as flow:
        outgoing = await anext(flow)
        if outgoing is not request:
            assert str(outgoing.url) == "https://oauth.test/decision-service/token"
            assert parse_qs(outgoing.content.decode())["refresh_token"] == ["old-refresh"]
            (folder / f"refresh-{client}").touch()
            await asyncio.sleep(0.25)
            outgoing = await flow.asend(
                httpx2.Response(
                    200,
                    json={
                        "access_token": "fresh-access",
                        "refresh_token": "new-refresh",
                        "expires_in": 3600,
                    },
                    request=outgoing,
                )
            )

        assert outgoing is request
        assert outgoing.headers.get("Authorization") == "Bearer fresh-access"
        (folder / f"resource-{client}").touch()
        # Each request remains in flight until both clients reach this point.
        await wait_for_file(folder / f"resource-{other}")
        try:
            await flow.asend(httpx2.Response(200, request=outgoing))
        except StopAsyncIteration:
            return
        raise AssertionError("Unexpected additional request in the OAuth flow")


@unittest.skipUnless(os.name == "nt", "Uses Windows file locking and temporary DPAPI state")
class SharedRefreshTest(unittest.TestCase):
    def test_two_clients_refresh_once_without_locking_resource_requests(self):
        with tempfile.TemporaryDirectory(prefix="dsh-oauth-test-") as temp:
            folder = Path(temp)
            asyncio.run(seed_storage(folder))
            processes = [
                subprocess.Popen(
                    [sys.executable, "-I", "-B", __file__, "--worker", temp, client, other],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for client, other in (("a", "b"), ("b", "a"))
            ]
            try:
                async def start_after_both_loaded():
                    await asyncio.gather(*(wait_for_file(folder / f"ready-{n}") for n in "ab"))
                    # Both workers hold the same expiring snapshot before the barrier opens.
                    (folder / "start").touch()

                time.sleep(1.1)
                asyncio.run(start_after_both_loaded())
                outputs = [process.communicate(timeout=18)[0] for process in processes]
                self.assertEqual(len(list(folder.glob("refresh-*"))), 1)
                self.assertEqual(len(list(folder.glob("resource-*"))), 2)
                for process, output in zip(processes, outputs):
                    self.assertEqual(process.returncode, 0, output)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        asyncio.run(exercise_client(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
    else:
        unittest.main()
