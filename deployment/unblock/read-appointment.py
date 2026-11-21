"""Emit one confirmed coordinator appointment for the restricted SSH reader."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


UNIT = "multica-backend.service"
INSTANCE = "tencent"
WORKSPACES = Path("/etc/multica-backend/unblock-reader-workspaces.json")
CONFIG = Path("/etc/multica-backend/config.json")
RUNNING_CONFIG = Path("/run/credentials") / UNIT / "config.json"
UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
COMMAND = re.compile(rf"read-appointment {INSTANCE} ({UUID})\n")
GENERATION = re.compile(r"[0-9a-f]{32}")
MAX_DOCUMENT_BYTES = 1024 * 1024


def _unique_fields(items):
    document = dict(items)
    if len(document) != len(items):
        raise ValueError("duplicate JSON field")
    return document


def _invalid_constant(value):
    raise ValueError(f"invalid JSON constant: {value}")


def _read_json(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        properties = os.fstat(stream.fileno())
        if (not stat.S_ISREG(properties.st_mode) or properties.st_uid != os.geteuid()
                or properties.st_mode & 0o022):
            raise ValueError("unsafe appointment configuration permissions")
        body = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(body) > MAX_DOCUMENT_BYTES:
        raise ValueError("appointment configuration exceeds size limit")
    return json.loads(body, object_pairs_hook=_unique_fields, parse_constant=_invalid_constant)


def _read_active_unit():
    snapshot = subprocess.run(
        ["/usr/bin/systemctl", "show", "--no-pager", "--timestamp=us",
         "--property=ActiveState,SubState,InvocationID,ActiveEnterTimestamp,ActiveEnterTimestampMonotonic",
         UNIT],
        check=True, capture_output=True, timeout=4, encoding="ascii",
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TZ": "UTC"},
    ).stdout
    values = _unique_fields([line.split("=", 1) for line in snapshot.splitlines()])
    if values.get("ActiveState") != "active" or values.get("SubState") != "running":
        raise ValueError("appointment authority is inactive")
    generation = values["InvocationID"]
    if not GENERATION.fullmatch(generation) or int(generation, 16) == 0:
        raise ValueError("invalid appointment authority generation")
    monotonic = values["ActiveEnterTimestampMonotonic"]
    if not monotonic.isascii() or not monotonic.isdecimal() or int(monotonic) <= 0:
        raise ValueError("invalid appointment authority activation")
    entered = datetime.strptime(values["ActiveEnterTimestamp"], "%a %Y-%m-%d %H:%M:%S.%f UTC")
    confirmed_since = entered.replace(tzinfo=timezone.utc).isoformat(timespec="microseconds")
    return generation, confirmed_since.replace("+00:00", "Z"), monotonic


def _coordinator(path, workspace):
    registrations = _read_json(path)["instances"][INSTANCE]["workspaces"]
    if not isinstance(registrations, dict) or any(not re.fullmatch(UUID, key) for key in registrations):
        raise ValueError("invalid workspace registration")
    value = registrations[workspace]["coordinator_id"]
    if not isinstance(value, str) or not re.fullmatch(UUID, value):
        raise ValueError("invalid coordinator identity")
    return value


def read_appointment(command, allowed_path, disk_path, running_path, read_unit):
    request = COMMAND.fullmatch(command)
    if request is None:
        raise ValueError("invalid original command")
    workspace = request[1]
    allowed = _read_json(allowed_path)
    if (not isinstance(allowed, list)
            or any(not isinstance(item, str) or not re.fullmatch(UUID, item) for item in allowed)
            or len(allowed) != len(set(allowed))
            or workspace not in allowed):
        raise ValueError("workspace absent or invalid in appointment reader grant")
    active = read_unit()
    coordinator = _coordinator(disk_path, workspace)
    if coordinator != _coordinator(running_path, workspace):
        raise ValueError("appointment disagrees with running authority")
    if active != read_unit() or coordinator != _coordinator(disk_path, workspace):
        raise ValueError("appointment authority changed during read")
    generation, confirmed_since, _ = active
    return {
        "instance_id": INSTANCE,
        "workspace_id": workspace,
        "coordinator_id": coordinator,
        "generation": generation,
        "confirmed_since": confirmed_since,
    }


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        print("appointment reader unavailable", file=sys.stderr)
        return 2
    try:
        command = sys.stdin.buffer.read(128).decode("ascii")
        result = read_appointment(command, WORKSPACES, CONFIG, RUNNING_CONFIG, _read_active_unit)
    except (KeyError, OSError, RecursionError, TypeError, ValueError, subprocess.SubprocessError):
        print("coordinator appointment unconfirmed", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
