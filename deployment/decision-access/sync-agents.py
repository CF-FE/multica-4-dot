"""Provision authorized Multica agents from an operator's authenticated CLI."""

import argparse
import json
from pathlib import Path
import secrets
import shlex
import subprocess
from urllib.parse import urlsplit
from uuid import UUID


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workspace", required=True, type=UUID)
parser.add_argument("--server-url", required=True, help="Multica HTTPS URL or local SSH tunnel")
parser.add_argument("--decision-ssh", required=True, help="SSH alias for the Decision Service host")
parser.add_argument("--apply", action="store_true")
parser.add_argument("--revoke-agent", type=UUID, help="Revoke a previously provisioned role after its MCP is disabled")
args = parser.parse_args()
origin = urlsplit(args.server_url)
if origin.scheme != "https" and not (origin.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1", "::1"}):
    parser.error("Use HTTPS or a local SSH tunnel")

key = "DECISION_AGENT_TOKEN"
library_name = "decision-service-agent"
legacy_name = "decision-service"
remote_program = Path(__file__).with_name("apply-caller.py").read_text()


def call(*parts, body=None, workspace=None):
    base = ["multica", "--server-url", args.server_url, "--workspace-id", str(workspace or args.workspace)]
    proc = subprocess.run([*base, *parts, "--output", "json"], input=body, capture_output=True, text=True, timeout=45)
    if proc.returncode:
        # The CLI can echo secret request values. Keep failures scoped to the command.
        raise RuntimeError(f"Multica {parts[0]} {parts[1]} exited with {proc.returncode}")
    return json.loads(proc.stdout)


def update_policy(request):
    proc = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", args.decision_ssh,
         "python3 -c " + shlex.quote(remote_program)],
        input=json.dumps(request), text=True, capture_output=True, timeout=90,
    )
    if proc.returncode:
        raise RuntimeError(f"Remote policy update failed for {request['agent_id']} (exit {proc.returncode})")
    return json.loads(proc.stdout)


workspace_ids = [str(UUID(w["id"])) for w in call("workspace", "list")]
if str(args.workspace) not in workspace_ids:
    raise SystemExit("Expected workspace missing from authenticated inventory")
project_ids = set()
for wid in workspace_ids:
    for row in call("project", "list", workspace=wid) + call("project", "list", "--archived", workspace=wid):
        if row["workspace_id"] != wid:
            raise SystemExit("Project inventory workspace mismatch")
        project_ids.add(str(UUID(row["id"])))
projects = sorted(project_ids)
servers = {s["name"]: s["id"] for s in call("workspace", "mcp", "list")}
if not projects or library_name not in servers:
    raise SystemExit("Project inventory or dedicated MCP library entry missing")
agents = call("agent", "list", "--include-archived") if args.revoke_agent else call("agent", "list")
if isinstance(agents, dict):
    agents = agents["agents"]
eligible = []
for agent in agents:
    aid = str(UUID(agent["id"]))
    attached = call("agent", "mcp", "list", aid)
    enabled = {s["name"] for s in attached if s["enabled"]}
    if enabled.intersection({legacy_name, library_name}):
        eligible.append((aid, enabled))
if args.revoke_agent:
    target = str(args.revoke_agent)
    if not any(a["id"] == target for a in agents) or any(aid == target for aid, _ in eligible):
        raise SystemExit("Revoke requires a known role with both Decision MCP entries disabled or removed")
    if args.apply:
        receipt = update_policy({"agent_id": target, "action": "revoke"})
        if receipt != {"caller_scope": "multica-agent-" + target, "project_count": 0, "bank_count": 0}:
            raise RuntimeError("Revocation readback failed")
        env = call("agent", "env", "get", target).get("custom_env") or {}
        if key in env:
            payload = {name: "****" for name in env if name != key}
            call("agent", "env", "set", target, "--custom-env-stdin", body=json.dumps(payload))
            if key in (call("agent", "env", "get", target).get("custom_env") or {}):
                raise RuntimeError("Agent credential removal readback failed")
    print(f"Revocation {'verified' if args.apply else 'available'} for {target}")
    raise SystemExit(0)
print(f"Projects: {len(projects)}. Eligible agents: {len(eligible)}.", flush=True)
for aid, enabled in eligible:
    if not args.apply:
        print(f"Eligible agent {aid}")
        continue
    env = call("agent", "env", "get", aid).get("custom_env") or {}
    token = env.get(key)
    if token is None:
        token = "mds_" + secrets.token_urlsafe(40)
        payload = {name: "****" for name in env}
        payload[key] = token
        call("agent", "env", "set", aid, "--custom-env-stdin", body=json.dumps(payload))
        actual = call("agent", "env", "get", aid)["custom_env"]
        if actual != {**env, key: token}:
            raise SystemExit(f"Custom environment readback differs for {aid}")
    if not isinstance(token, str) or not token.startswith("mds_") or len(token) < 50:
        raise SystemExit(f"Existing environment key has unknown ownership for {aid}")
    request = {"agent_id": aid, "project_ids": projects, "token": token}
    receipt = update_policy(request)
    if receipt != {"caller_scope": "multica-agent-" + aid, "project_count": len(projects), "bank_count": 0}:
        raise RuntimeError("Unexpected service policy receipt")
    if library_name not in enabled:
        call("agent", "mcp", "add", aid, servers[library_name])
        call("agent", "mcp", "enable", aid, servers[library_name])
    if legacy_name in enabled:
        call("agent", "mcp", "disable", aid, servers[legacy_name])
    final = {s["name"] for s in call("agent", "mcp", "list", aid) if s["enabled"]}
    if final != (enabled - {legacy_name}) | {library_name}:
        raise RuntimeError(f"MCP assignment readback differs for {aid}")
    print(f"Verified agent {aid}, {len(projects)} projects and 0 banks.", flush=True)
