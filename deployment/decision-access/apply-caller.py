"""Apply one Multica agent policy on the Decision Service host. Input is private stdin."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from uuid import UUID


config = Path("/etc/decision-service/config.json")


def save(data, stat):
    with tempfile.NamedTemporaryFile(dir=config.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            os.fchown(f.fileno(), stat.st_uid, stat.st_gid)
            os.fchmod(f.fileno(), stat.st_mode & 0o777)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            os.replace(tmp, config)
        finally:
            tmp.unlink(missing_ok=True)


def restart():
    subprocess.run(["systemctl", "restart", "decision-service.service"], check=True)
    for attempt in range(25):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8768/health", timeout=2) as r:
                if json.load(r).get("status") == "ok":
                    return
        except OSError:
            pass
        time.sleep(0.4)
    raise RuntimeError("Decision Service health check failed")


request = json.load(sys.stdin)
scope = "multica-agent-" + str(UUID(request["agent_id"]))
revoke = request.get("action") == "revoke"
projects = sorted({str(UUID(p)) for p in request.get("project_ids", [])})
token = request.get("token")
if not revoke and (not projects or not isinstance(token, str) or not token.startswith("mds_") or len(token) < 50):
    raise SystemExit("Invalid provisioning input")
with (config.parent / ".multica-caller.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    original = config.read_bytes()
    stat = config.stat()
    data = json.loads(original)
    callers = data["callers"]
    if scope in data.get("github_oauth", {}).get("principals", {}).values():
        raise SystemExit("Dedicated identity already belongs to an OAuth login")
    matching = [k for k, c in callers.items() if c["caller_scope"] == scope]
    if not revoke and any(k != token for k in matching):
        raise SystemExit("Existing identity has a different credential; reconcile before rotating")
    if token in callers and callers[token]["caller_scope"] != scope:
        raise SystemExit("Credential belongs to another identity")
    policy = {"caller_scope": scope, "project_ids": projects, "bank_ids": []}
    if revoke:
        for k in matching:
            del callers[k]
    else:
        callers[token] = policy
    if callers != json.loads(original)["callers"]:
        updated = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        if config.read_bytes() != original:
            raise SystemExit("Configuration changed during provisioning")
        save(updated, stat)
        try:
            restart()
        except Exception:
            if config.read_bytes() == updated:
                save(original, stat)
                restart()
            raise
    stored = json.loads(config.read_bytes())
    remaining = [c for c in stored["callers"].values() if c["caller_scope"] == scope]
    if remaining != ([] if revoke else [policy]):
        raise SystemExit("Policy readback failed")
    print(json.dumps({"caller_scope": scope, "project_count": len(projects), "bank_count": 0}))
