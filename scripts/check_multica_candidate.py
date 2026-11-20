"""Check pinned Multica versions by fixture, official source, or isolated native router."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from time import monotonic, sleep


ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "compatibility" / "candidate_versions.json"
GO_TEST = ROOT / "compatibility" / "candidate_native_test.go"
UPSTREAM = "https://github.com/multica-ai/multica.git"
CONTENTS = "https://api.github.com/repos/multica-ai/multica/contents"
NATIVE_TESTS = {
    "TestCandidateIdentity": "identity",
    "TestCandidateOwnership": "project_issue_run_ownership",
    "TestCandidateScopeDenial": "cross_workspace_read_and_write_denied",
    "TestCandidateSilentComment": "silent_comment_saved_without_run",
    "TestCandidateNormalComment": "normal_comment_receipt_and_run",
}
ROUTER = "server/cmd/server/router.go"
COMMENTS = "server/internal/handler/comment.go"
RUNS = "server/internal/handler/daemon.go"
SOURCE_RULES = {
    "registered_routes": (ROUTER, (
        'r.Get("/api/me", h.GetMe)', 'r.Route("/api/projects"', 'r.Get("/", h.GetProject)',
        'r.Route("/api/issues"', 'r.Get("/", h.GetIssue)', 'r.Post("/comments", h.CreateComment)',
        'r.Get("/task-runs", h.ListTasksByIssue)',
    )),
    "issue_scoped_run_handler": (RUNS, (
        'func (h *Handler) ListTasksByIssue(', 'h.loadIssueForUser(w, r, issueID)',
        'scope != "issue"', 'view != "timeline"', 'issueTimelineTaskResponse(resp[i])',
    )),
    "comment_silence_and_receipt_code": (COMMENTS, (
        'const noteCommentPrefix = "/note"', 'if isNoteComment(comment.Content) {\n\t\treturn nil',
        'resp.TriggerOutcomes = h.triggerTasksForComment(', 'json:"trigger_outcomes,omitempty"',
    )),
}


class CheckError(Exception):
    pass


def command(args, *, cwd=None, env=None, timeout=120):
    try:
        return subprocess.run(args, cwd=cwd, env=env, timeout=timeout, text=True,
                              capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise CheckError(f"missing executable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CheckError(f"command timed out: {args[0]}") from exc


def checked(args, stage, *, cwd=None, env=None, timeout=120):
    proc = command(args, cwd=cwd, env=env, timeout=timeout)
    if proc.returncode:
        # Subprocess stderr can contain temporary credentials and fixture bodies.
        raise CheckError(f"{stage}: exit {proc.returncode}")
    return proc.stdout.strip()


def source_checks(sources):
    checks = {}
    for name, (path, markers) in SOURCE_RULES.items():
        if path not in sources:
            checks[name] = "unknown"
        else:
            checks[name] = "pass" if all(marker in sources[path] for marker in markers) else "fail"
    return checks


def check_sources(version, source_dir):
    sources, errors = {}, []
    for path in sorted({path for path, _ in SOURCE_RULES.values()}):
        try:
            if source_dir is not None:
                body = (source_dir / version["commit"] / path).read_bytes()
            else:
                proc = command(["curl", "--disable", "--fail", "--silent", "--show-error", "--compressed",
                                "--retry", "1", "--max-time", "45", "-H", "Accept: application/vnd.github.raw+json",
                                "-H", "X-GitHub-Api-Version: 2026-03-10",
                                f"{CONTENTS}/{path}?ref={version['commit']}"], timeout=100)
                if proc.returncode:
                    http = re.search(r"returned error: ([45][0-9]{2})", proc.stderr)
                    diagnostic = f"HTTP {http[1]}" if http else f"curl exit {proc.returncode}"
                    raise CheckError(f"read source {path}: {diagnostic}")
                body = proc.stdout.encode("utf-8")
            if hashlib.sha256(body).hexdigest() != version["source_sha256"][path]:
                raise CheckError(f"read source {path}: SHA-256 mismatch")
            sources[path] = body.decode("utf-8")
        except CheckError as exc:
            errors.append(str(exc))
        except OSError:
            errors.append(f"read source {path}: local snapshot unavailable")
    return source_checks(sources), ", ".join(errors)


def native_results(stream, returncode):
    started = set()
    results = dict.fromkeys(NATIVE_TESTS.values(), "unknown")
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        test = event.get("Test")
        if test not in NATIVE_TESTS:
            continue
        action = event.get("Action")
        if action == "run":
            started.add(test)
        elif test in started and action in {"pass", "fail"}:
            results[NATIVE_TESTS[test]] = action
    return results, returncode == 0 and set(results.values()) == {"pass"}


def local_docker(socket):
    if not socket.is_absolute() or not socket.is_socket():
        raise CheckError("local Docker Unix socket unavailable")
    docker = ["docker", "--host", f"unix://{socket}"]
    # An explicit socket is the only accepted Docker destination.
    env = {key: value for key, value in os.environ.items() if key not in ("DOCKER_HOST", "DOCKER_CONTEXT")}
    checked([*docker, "version", "--format", "{{.Server.Version}}"], "local Docker daemon", env=env)
    return docker, env


def run_native(version, image_id, docker, docker_env, temp):
    checkout = temp / version["tag"]
    checked(["git", "-c", "core.hooksPath=/dev/null", "clone", "--quiet", "--depth=1", "--single-branch",
             f"--branch={version['tag']}", UPSTREAM, str(checkout)], "clone pinned upstream", timeout=600)
    commit = checked(["git", "rev-parse", "HEAD"], "resolve checked-out commit", cwd=checkout)
    if commit != version["commit"]:
        raise CheckError("official tag does not match the pinned commit")
    server = checkout / "server"
    shutil.copyfile(GO_TEST, server / "cmd" / "server" / GO_TEST.name)
    password = secrets.token_hex(16)
    name = f"multica-candidate-{secrets.token_hex(8)}"
    started = False
    try:
        checked([*docker, "run", "--detach", "--rm", "--name", name, "--publish", "127.0.0.1::5432",
                 "--tmpfs", "/var/lib/postgresql/data", "--env", "POSTGRES_PASSWORD",
                 "--env", "POSTGRES_USER=multica", "--env", "POSTGRES_DB=multica", image_id],
                "start disposable PG17", env={**docker_env, "POSTGRES_PASSWORD": password})
        started = True
        bind = checked([*docker, "port", name, "5432/tcp"], "read assigned PG port", env=docker_env)
        address, _, port = bind.rpartition(":")
        if address != "127.0.0.1" or not port.isascii() or not port.isdecimal() or not 0 < int(port) < 65536:
            raise CheckError("PG17 was not published on a single IPv4 loopback port")
        deadline = monotonic() + 60
        while command([*docker, "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "multica", "-d", "multica"],
                      timeout=5, env=docker_env).returncode:
            if monotonic() >= deadline:
                raise CheckError("disposable PG17 readiness timed out")
            sleep(1)

        go_env = {
            "PATH": os.environ["PATH"], "GOENV": "off", "GOWORK": "off", "GOTOOLCHAIN": "local",
            "GOMODCACHE": str(temp / "go-mod"), "GOCACHE": str(temp / "go-build"),
            "DATABASE_URL": f"postgres://multica:{password}@127.0.0.1:{port}/multica?sslmode=disable",
            "JWT_SECRET": secrets.token_hex(32),
        }
        checked(["go", "run", "./cmd/migrate", "up"], "apply pinned upstream migrations", cwd=server,
                env=go_env, timeout=900)
        tests = "^(" + "|".join(NATIVE_TESTS) + ")$"
        proc = command(["go", "test", "-count=1", "-json", "-run", tests, "./cmd/server"], cwd=server,
                       env=go_env, timeout=900)
        checks, passed = native_results(proc.stdout, proc.returncode)
        detail = None if passed else f"go test exit {proc.returncode}; inspect the named check results"
        return checks, detail
    finally:
        removed = command([*docker, "rm", "--force", "--volumes", name], env=docker_env, timeout=30)
        if started and removed.returncode:
            raise CheckError(f"could not confirm removal of disposable container {name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--source", action="store_true", help="check routes and guards in pinned official source")
    mode.add_argument("--isolated", action="store_true", help="migrate and test both versions against fresh local PG17")
    parser.add_argument("--source-dir", type=Path, help="verify local snapshots at <dir>/<commit>/<upstream-path>")
    parser.add_argument("--docker-socket", type=Path, default=Path("/var/run/docker.sock"))
    args = parser.parse_args(argv)
    if args.source_dir is not None and not args.source:
        parser.error("--source-dir requires --source")
    if not args.source and not args.isolated:
        return subprocess.call([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests",
                                "-p", "test_multica_candidate.py"], cwd=ROOT)

    metadata = json.loads(META.read_text(encoding="utf-8"))
    evidence = "native_source_router" if args.isolated else "fixed_source_inspection"
    report = {
        "schema_version": 1, "evidence": evidence,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release_image_compatibility": "unknown", "versions": [],
    }
    cases = NATIVE_TESTS.values() if args.isolated else SOURCE_RULES
    for role in ("baseline", "candidate"):
        version = metadata[role]
        report["versions"].append({
            "role": role, "tag": version["tag"], "commit": version["commit"], "status": "not_run",
            "checks": dict.fromkeys(cases, "unknown"),
        })
    try:
        if args.isolated:
            docker, env = local_docker(args.docker_socket)
            image = metadata["postgres_image"]
            checked([*docker, "pull", image], "pull public PG17 fixture image", env=env, timeout=600)
            image_id = checked([*docker, "image", "inspect", "--format", "{{.Id}}", image], "resolve PG17 image", env=env)
            report["postgres_image"] = {"reference": image, "image_id": image_id}
        with tempfile.TemporaryDirectory(prefix="multica-candidate-") as temp:
            for row in report["versions"]:
                version = metadata[row["role"]]
                try:
                    if args.isolated:
                        row["checks"], detail = run_native(version, image_id, docker, env, Path(temp))
                    else:
                        row["checks"], detail = check_sources(version, args.source_dir)
                    states = set(row["checks"].values())
                    if "fail" in states or (args.isolated and detail):
                        row["status"] = "fail" if states != {"unknown"} else "not_run"
                    elif states == {"pass"}:
                        row["status"] = "pass"
                    if detail:
                        row["detail"] = detail
                except CheckError as exc:
                    row.update(status="not_run", detail=str(exc))
    except CheckError as exc:
        report["detail"] = str(exc)
    statuses = {row["status"] for row in report["versions"]}
    status = "pass" if statuses == {"pass"} else "fail" if "fail" in statuses else "not_run"
    print(json.dumps({**report, "status": status}, ensure_ascii=False, sort_keys=True))
    return {"pass": 0, "fail": 1, "not_run": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
