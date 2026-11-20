"""Call the approved win-work project proxy from the current task directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Timer


ALLOWED = {"recall", "get_document", "retain", "get_operation"}


def rpc(process, number, method, params):
    message = {"jsonrpc": "2.0", "method": method, "params": params}
    if number is not None:
        message["id"] = number
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    if number is None:
        return
    for line in process.stdout:
        response = json.loads(line)
        if response.get("id") == number:
            if "error" in response:
                raise RuntimeError("MCP error " + str(response["error"].get("code")))
            return response["result"]
    raise RuntimeError("The project proxy exited or timed out")


def body(result):
    value = result.get("structuredContent")
    if value is None:
        value = next((item["text"] for item in result.get("content", [])
                      if item.get("type") == "text"), None)
    for _ in range(4):
        if isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        elif isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                break
        else:
            break
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=sorted(ALLOWED | {"tools"}))
    parser.add_argument("--receipt", action="store_true", help="Only print IDs, counts and status")
    args = parser.parse_args()
    if os.name != "nt":
        raise RuntimeError("This helper is for win-work Kimi sessions")
    interpreter = Path("D:/Hindsight/app/.venv/Scripts/python.exe")
    proxy = Path.home() / ".kimi-code" / "hindsight" / "project_memory.py"
    if not interpreter.is_file() or not proxy.is_file():
        raise RuntimeError("The approved win-work Hindsight interpreter or project proxy is missing")
    payload = {} if args.tool == "tools" else json.load(sys.stdin.buffer)
    if not isinstance(payload, dict):
        raise ValueError("Tool arguments must be a JSON object")
    process = subprocess.Popen(
        [str(interpreter), "-I", "-B", "-X", "utf8", str(proxy), "mcp"],
        cwd=Path.cwd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
    )
    timer = Timer(45, process.kill)
    timer.daemon = True
    timer.start()
    try:
        rpc(process, 1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "clientInfo": {"name": "hindsight-memory", "version": "1"}})
        rpc(process, None, "notifications/initialized", {})
        available = {tool["name"]: tool.get("inputSchema", {})
                     for tool in rpc(process, 2, "tools/list", {})["tools"]}
        if args.tool == "tools":
            return {name: schema for name, schema in available.items() if name in ALLOWED}
        if args.tool not in available:
            raise RuntimeError("Tool unavailable in this project context: " + args.tool)
        result = rpc(process, 3, "tools/call", {"name": args.tool, "arguments": payload})
        value = body(result)
        if result.get("isError") or isinstance(value, dict) and value.get("error"):
            raise RuntimeError("The configured project proxy declined or failed " + args.tool)
        if args.receipt:
            if not isinstance(value, dict):
                raise RuntimeError("The project proxy returned no structured receipt")
            receipt = {k: value[k] for k in ("id", "document_id", "bank_id", "operation_id",
                       "status", "memory_unit_count") if k in value}
            if isinstance(value.get("results"), list):
                receipt["result_count"] = len(value["results"])
            return receipt
        return value
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        timer.cancel()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(main(), ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        sys.exit(str(exc))
