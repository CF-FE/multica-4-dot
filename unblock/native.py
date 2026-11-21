"""Read one registered Multica thread and reconcile its coordinator reminder."""

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
from threading import Lock

try:
    from multica_backend.mailbox import Mailbox, MailboxError
    from multica_backend.multica_api import CONTRACT_BASELINE, CONTRACT_SOURCE_COMMIT, _parse_origin, _uuid
    from multica_backend.native_http import NativeHTTP, NativeHTTPError
except ModuleNotFoundError as exc:
    if exc.name != "multica_backend":
        raise
    # Direct checkout use with the standard library and no MCP SDK installed.
    from mcp.multica_backend.mailbox import Mailbox, MailboxError
    from mcp.multica_backend.multica_api import CONTRACT_BASELINE, CONTRACT_SOURCE_COMMIT, _parse_origin, _uuid
    from mcp.multica_backend.native_http import NativeHTTP, NativeHTTPError


_SCOPE = ("instance_id", "workspace_id", "project_id", "issue_id", "thread_id", "coordinator_id")
_MARKER = re.compile(r"unblock\.v1:[0-9a-f]{64}")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SUMMARY = "/note unblock.v1 "
_EVIDENCE = "/note unblock.evidence.v1 "
_REMINDER = (
    "核收原卡登记检查点的新线索或到期事项。请在原线程核对现任岗位、原卡状态和已有在途，"
    "按原授权记静默摘要。此提醒仅请求核收，不授予派发、恢复、写入外部系统或验收的权限。"
)
_TERMINAL = {"completed", "failed", "cancelled"}
_IN_FLIGHT = {"queued", "deferred", "dispatched", "running", "waiting_local_directory"}
_OPEN_ISSUE_CATEGORIES = ("backlog", "todo", "in_progress", "in_review", "blocked")
_TERMINAL_ISSUE_CATEGORIES = ("done", "cancelled")
_INCOMPLETE_COMMENTS = (
    "X-Comments-Truncated", "X-Multica-Next-Before", "X-Multica-Next-Before-Id",
)


class NativeSourceError(ValueError):
    """A fixed diagnostic that can be reported without exposing remote content."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _json_object(raw, failure):
    def unique_fields(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("duplicate member")
        return result

    def invalid_constant(_):
        raise ValueError("invalid JSON constant")

    try:
        result = json.loads(raw, object_pairs_hook=unique_fields, parse_constant=invalid_constant)
        if isinstance(result, dict):
            # Also reject infinities produced by exponent overflow and invalid Unicode.
            json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")
            return result
    except (ValueError, RecursionError):
        pass
    raise NativeSourceError(failure)


def _time(value):
    if isinstance(value, str) and "T" in value:
        try:
            result = datetime.fromisoformat(value)
            if result.utcoffset() is not None:
                return result
        except (ValueError, OverflowError):
            pass
    raise NativeSourceError("invalid_source_timestamp")


def _token(value, failure):
    if isinstance(value, str) and _TOKEN.fullmatch(value):
        return value
    raise NativeSourceError(failure)


def _id(value, field):
    try:
        return _uuid(value, "configuration", field)
    except NativeHTTPError:
        raise NativeSourceError(f"invalid_uuid:{field}") from None


class NativeSource:
    """Read and remind on a frozen registration. The caller owns persistent send claims."""

    def __init__(self, registration: Mapping):
        if not isinstance(registration, Mapping):
            raise NativeSourceError("invalid_registration")
        self._scope = {
            field: _id(registration.get(field), field) for field in _SCOPE[1:]
        }
        self._scope["instance_id"] = _token(registration.get("instance_id"), "invalid_instance_id")
        self._user_id = _id(registration.get("expected_user_id"), "expected_user_id")
        self._origin = registration.get("origin")
        self._allow_private_http = registration.get("allow_private_http", False)
        self._enabled = registration.get("notifications_enabled", False)
        if type(self._enabled) is not bool or type(self._allow_private_http) is not bool:
            raise NativeSourceError("invalid_registration_switch")
        try:
            self._origin_identity = _parse_origin(self._origin, self._allow_private_http)
        except NativeHTTPError as exc:
            raise NativeSourceError(exc.code) from None
        profile = registration.get("cli_profile")
        if not isinstance(profile, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", profile):
            raise NativeSourceError("invalid_cli_profile")
        path = registration.get("cli_path")
        if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
            raise NativeSourceError("invalid_cli_path")
        self._cli_path, self._profile = path, profile
        self._workspace = self._scope["workspace_id"]
        self._project = self._scope["project_id"]
        self._issue = self._scope["issue_id"]
        self._thread = self._scope["thread_id"]
        self._coordinator = self._scope["coordinator_id"]
        self._checkpoint = registration.get("checkpoint_id")
        if self._checkpoint is not None:
            _token(self._checkpoint, "invalid_registered_checkpoint")
        roles = registration.get("roles")
        self._coordinator_term = None
        if roles is not None:
            role = roles.get("coordinator") if isinstance(roles, dict) else None
            if not isinstance(role, dict) or role.get("id") != self._coordinator:
                raise NativeSourceError("coordinator_registration_mismatch")
            end = role.get("valid_until")
            self._coordinator_term = (
                _time(role.get("valid_from")), _time(end) if end is not None else None,
            )
        self._issue_path = f"/api/issues/{self._issue}"
        self._wakeup_path = f"{self._issue_path}/wakeups"
        self._run_id = registration.get("run_id")
        if self._run_id is not None:
            self._run_id = _id(self._run_id, "run_id")
        self._mailbox_ref = registration.get("mailbox")
        if self._mailbox_ref is not None:
            job = self._mailbox_ref
            if not isinstance(job, dict) or set(job) != {"job_id", "payload_hash", "recipient"}:
                raise NativeSourceError("invalid_mailbox_registration")
            _token(job["job_id"], "invalid_mailbox_job_id")
            if not isinstance(job["payload_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", job["payload_hash"]):
                raise NativeSourceError("invalid_mailbox_payload_hash")
            recipient = job["recipient"]
            if not isinstance(recipient, str) or not recipient or recipient != recipient.strip() or not recipient.isprintable():
                raise NativeSourceError("invalid_mailbox_recipient")
            self._mailbox_ref = dict(job)
        authors = registration.get("supplement_authors", [])
        if not isinstance(authors, list):
            raise NativeSourceError("invalid_supplement_authors")
        self._authors = set()
        for author in authors:
            if not isinstance(author, dict) or set(author) != {"id", "type"} or author["type"] not in ("member", "agent"):
                raise NativeSourceError("invalid_supplement_author")
            actor_id = _id(author["id"], "supplement_author_id")
            if (author["type"], actor_id) != ("agent", self._coordinator):
                self._authors.add((author["type"], actor_id))
        self._http = None
        self._poll_basis = None
        self._attempted = set()
        self._lock = Lock()

    def _cli(self, *args):
        # Ignore Run, token, server-override and proxy variables. These two
        # commands inspect the local binary and named profile without a login.
        env = {key: os.environ[key] for key in ("HOME", "USERPROFILE", "SYSTEMROOT", "XDG_CONFIG_HOME")
               if key in os.environ}
        try:
            result = subprocess.run(
                [self._cli_path, "--profile", self._profile, *args], env=env, stdin=subprocess.DEVNULL,
                capture_output=True, encoding="utf-8", timeout=10, check=True,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError):
            raise NativeSourceError("cli_read_failed") from None
        if result.stderr.strip() or len(result.stdout) > 65536:
            raise NativeSourceError("cli_read_failed")
        return result.stdout

    def _request(self, method, path, *, body=None, incomplete_headers=()):
        try:
            return self._http.request(
                method, path, workspace_id=None if path == "/api/me" else self._workspace,
                body=body, incomplete_headers=incomplete_headers,
            )
        except NativeHTTPError as exc:
            raise NativeSourceError(f"multica:{exc.code}") from None

    def _get(self, path, expected_type, *, incomplete_headers=()):
        result = self._request("GET", path, incomplete_headers=incomplete_headers)
        if not isinstance(result, expected_type):
            raise NativeSourceError("invalid_native_response")
        return result

    def _bind(self):
        version = self._cli("--version").splitlines()
        expected = f"multica {CONTRACT_BASELINE.removeprefix('v')} (commit: {CONTRACT_SOURCE_COMMIT[:9]}, "
        if not version or not version[0].startswith(expected):
            raise NativeSourceError("unsupported_cli_version")
        config = self._cli("config", "show")
        profiles = re.findall(r"(?m)^Profile:\s+([^\r\n]+)$", config)
        origins = re.findall(r"(?m)^server_url:\s+([^\r\n]+)$", config)
        if profiles != [self._profile] or len(origins) != 1:
            raise NativeSourceError("profile_binding_unknown")
        try:
            actual = _parse_origin(origins[0], self._allow_private_http)
        except NativeHTTPError:
            raise NativeSourceError("profile_binding_unknown") from None
        if actual != self._origin_identity:
            raise NativeSourceError("profile_origin_mismatch")
        token = os.environ.get("MULTICA_UNBLOCK_ACCESS_TOKEN", "")
        if not token.startswith("mul_"):
            raise NativeSourceError("multica_credential_unavailable")
        try:
            self._http = NativeHTTP(origin=self._origin, token=token, allow_private_http=self._allow_private_http)
        except NativeHTTPError as exc:
            raise NativeSourceError(f"multica:{exc.code}") from None
        if self._get("/api/me", dict).get("id") != self._user_id:
            raise NativeSourceError("identity_mismatch")
        project = self._get(f"/api/projects/{self._project}", dict)
        issue = self._get(self._issue_path, dict)
        if (project.get("id") != self._project or project.get("workspace_id") != self._workspace
                or issue.get("id") != self._issue or issue.get("workspace_id") != self._workspace
                or issue.get("project_id") != self._project):
            raise NativeSourceError("issue_scope_mismatch")
        agent = self._get(f"/api/agents/{self._coordinator}", dict)
        if (agent.get("id") != self._coordinator or agent.get("workspace_id") != self._workspace
                or agent.get("system_key") != "mika" or agent.get("archived_at") is not None):
            raise NativeSourceError("coordinator_changed")
        _token(issue.get("status"), "invalid_issue_status")
        return issue

    def _thread_rows(self):
        rows = self._get(f"{self._issue_path}/comments?thread={self._thread}", list,
                         incomplete_headers=_INCOMPLETE_COMMENTS)
        by_id = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("issue_id") != self._issue:
                raise NativeSourceError("comment_scope_mismatch")
            row_id = _id(row.get("id"), "comment_id")
            if row_id in by_id or "parent_id" not in row:
                raise NativeSourceError("ambiguous_thread")
            if (row.get("content_truncated", False) is not False or row.get("folded_count", 0) != 0):
                raise NativeSourceError("incomplete_thread")
            by_id[row_id] = row
        root = by_id.get(self._thread)
        if root is None or root["parent_id"] is not None or root.get("deleted_at") is not None:
            raise NativeSourceError("thread_root_unconfirmed")
        verified = {self._thread}
        for row_id in by_id:
            path = set()
            while row_id not in verified:
                if row_id not in by_id or row_id in path:
                    raise NativeSourceError("comment_thread_mismatch")
                path.add(row_id)
                row_id = _id(by_id[row_id]["parent_id"], "parent_id")
            verified.update(path)
        return rows

    def _summary(self, rows):
        by_round = {}
        candidates = []
        for row in rows:
            content = row.get("content")
            if (row.get("type") != "comment" or row.get("deleted_at") is not None
                    or not isinstance(content, str) or not content.startswith(_SUMMARY)
                    or row.get("author_type") != "agent" or row.get("author_id") != self._coordinator):
                continue
            snapshot = _json_object(content[len(_SUMMARY):], "invalid_summary")
            if any(snapshot.get(key) != expected for key, expected in self._scope.items()):
                raise NativeSourceError("summary_scope_mismatch")
            revision = snapshot.get("revision")
            checkpoint = _token(snapshot.get("checkpoint_id"), "invalid_checkpoint")
            if type(revision) is not int or revision < 1:
                raise NativeSourceError("invalid_summary_revision")
            created = _time(row.get("created_at"))
            if _time(row.get("updated_at")) != created:
                raise NativeSourceError("edited_summary")
            if "recorded_at" in snapshot and _time(snapshot["recorded_at"]) > created:
                raise NativeSourceError("summary_recorded_after_publication")
            round_rows = by_round.setdefault(checkpoint, {})
            if revision in round_rows:
                raise NativeSourceError("ambiguous_summary_revision")
            round_rows[revision] = created
            candidates.append((created, row, snapshot))
        if not candidates:
            raise NativeSourceError("coordinator_summary_unconfirmed")
        for revisions in by_round.values():
            times = [revisions[revision] for revision in sorted(revisions)]
            if any(previous >= current for previous, current in zip(times, times[1:])):
                raise NativeSourceError("summary_revision_out_of_order")
        candidates.sort(key=lambda row: row[0])
        if len(candidates) > 1 and candidates[-1][0] == candidates[-2][0]:
            raise NativeSourceError("ambiguous_current_summary")
        created, comment, snapshot = candidates[-1]
        if self._checkpoint is not None and snapshot["checkpoint_id"] != self._checkpoint:
            raise NativeSourceError("registered_checkpoint_changed")
        if self._coordinator_term is not None:
            start, end = self._coordinator_term
            if created < start or (end is not None and created >= end):
                raise NativeSourceError("summary_outside_coordinator_appointment")
        source = {
            "comment_id": comment["id"],
            "author_id": comment["author_id"],
            "created_at": comment["created_at"],
        }
        return created, source, snapshot

    def _issue_runs(self):
        runs = self._get(f"{self._issue_path}/task-runs?scope=issue&view=timeline", list,
                         incomplete_headers=("X-Active-Runs-Truncated",))
        by_id = {}
        for row in runs:
            if (not isinstance(row, dict) or row.get("issue_id") != self._issue
                    or row.get("workspace_id") != self._workspace
                    or row.get("project_id", self._project) != self._project
                    or row.get("restricted", False) is not False):
                raise NativeSourceError("run_scope_unconfirmed")
            run_id = _id(row.get("id"), "run_id")
            if run_id in by_id:
                raise NativeSourceError("duplicate_run")
            _id(row.get("agent_id"), "run_agent_id")
            status = row.get("status")
            if not isinstance(status, str) or not status:
                raise NativeSourceError("invalid_run_status")
            by_id[run_id] = row
        return by_id

    def _mailbox_hint(self, snapshot):
        baseline = snapshot.get("mailbox_result_version")
        if type(baseline) is not int or not 0 <= baseline < 2**63:
            raise NativeSourceError("mailbox_watermark_unconfirmed")
        mailbox = Mailbox.from_env()
        job = mailbox.verify_job(
            **self._mailbox_ref, instance_id=self._scope["instance_id"],
            workspace_id=self._workspace, project_id=self._project, coordinator_id=self._coordinator,
        )
        latest = job["latest_result_version"]
        if latest < baseline:
            raise NativeSourceError("mailbox_version_regressed")
        if latest > baseline:
            return f"mailbox:{job['job_id']}:{latest}"
        return None

    def poll(self) -> dict:
        """Return a verified snapshot and post-summary hints from its registered sources."""
        with self._lock:
            self._poll_basis = None
            issue = self._bind()
            rows = self._thread_rows()
            created, summary_source, snapshot = self._summary(rows)
            hints, pending = [], []
            for row in rows:
                content = row.get("content")
                author = row.get("author_type"), row.get("author_id")
                if (row.get("type") != "comment" or row.get("deleted_at") is not None
                        or not all(isinstance(value, str) for value in author) or author not in self._authors
                        or not isinstance(content, str) or not content.startswith(_EVIDENCE)):
                    continue
                posted = _time(row.get("created_at"))
                if posted < created:
                    continue
                if _time(row.get("updated_at")) != posted:
                    pending.append("comment:edited_supplement")
                    continue
                evidence = _json_object(content[len(_EVIDENCE):], "invalid_supplement")
                if (all(evidence.get(key) == expected for key, expected in self._scope.items())
                        and evidence.get("checkpoint_id") == snapshot["checkpoint_id"]):
                    ref = evidence.get("evidence_ref")
                    if not isinstance(ref, str) or not ref.strip() or len(ref) > 4096:
                        pending.append("comment:evidence_reference_unconfirmed")
                    else:
                        hints.append(f"comment:{row['id']}")
            if self._run_id is not None:
                try:
                    run = self._issue_runs().get(self._run_id)
                    if run is None:
                        raise NativeSourceError("exact_run_unconfirmed")
                    if run["status"] in _TERMINAL and _time(run.get("completed_at")) >= created:
                        hints.append(f"run:{self._run_id}:{run['status']}")
                except NativeSourceError as exc:
                    pending.append(f"run:{exc}")
            if self._mailbox_ref is not None:
                try:
                    hint = self._mailbox_hint(snapshot)
                    if hint is not None:
                        hints.append(hint)
                except MailboxError as exc:
                    pending.append(f"mailbox:{exc.code}")
                except NativeSourceError as exc:
                    pending.append(f"mailbox:{exc}")
            if not pending:
                self._poll_basis = dict(summary_source), deepcopy(snapshot), issue["status"]
            return {
                "snapshot": snapshot, "hints": sorted(hints), "pending": sorted(set(pending)),
                "summary_source": summary_source,
            }

    def _instruction(self, marker):
        if not isinstance(marker, str) or not _MARKER.fullmatch(marker):
            raise NativeSourceError("invalid_reminder_marker")
        binding = {
            **self._scope, "marker": marker, "type": "coordinator-checkpoint-review",
            "source": "registered-issue-thread", "issuer": self._user_id,
        }
        return json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n" + _REMINDER

    def _wakeup_rows(self):
        rules = self._get(self._wakeup_path, list)
        seen = set()
        for rule in rules:
            if (not isinstance(rule, dict) or rule.get("workspace_id") != self._workspace
                    or rule.get("issue_id") != self._issue or "parent_comment_id" not in rule):
                raise NativeSourceError("wakeup_scope_mismatch")
            rule_id = _id(rule.get("id"), "wakeup_id")
            _id(rule.get("agent_id"), "wakeup_agent_id")
            if rule_id in seen:
                raise NativeSourceError("duplicate_wakeup")
            seen.add(rule_id)
            if rule["parent_comment_id"] is not None:
                _id(rule["parent_comment_id"], "wakeup_parent_comment_id")
            if (not isinstance(rule.get("instruction"), str) or type(rule.get("enabled")) is not bool
                    or (rule.get("last_task_status") is not None and not isinstance(rule["last_task_status"], str))):
                raise NativeSourceError("invalid_wakeup_response")
        return rules

    def _matching_wakeup(self, marker, instruction, rules):
        matches = []
        for rule in rules:
            stored = rule["instruction"]
            if marker not in stored:
                continue
            if (stored != instruction or rule.get("agent_id") != self._coordinator
                    or rule.get("parent_comment_id") != self._thread or rule.get("created_by") != self._user_id
                    or rule.get("source_task_id") is not None or rule.get("created_by_agent") is not False
                    or rule.get("kind") != "event" or rule.get("event_types") != ["issue.status_changed"]
                    or rule.get("mode") != "once" or rule.get("on_timeout") != "end"
                    or rule.get("expiry_seconds") != 60
                    or type(rule.get("revision")) is not int or rule["revision"] != 1):
                raise NativeSourceError("wakeup_marker_conflict")
            condition = rule.get("condition")
            if (not isinstance(condition, dict) or set(condition) != {"type", "field", "value"}
                    or condition.get("type") != "issue_field" or condition.get("field") != "status"
                    or not isinstance(condition.get("value"), str)
                    or not 0 < (_time(rule.get("expires_at")) - _time(rule.get("created_at"))).total_seconds() <= 60):
                raise NativeSourceError("wakeup_marker_conflict")
            matches.append(rule)
        if len(matches) > 1:
            raise NativeSourceError("ambiguous_wakeup")
        return matches[0] if matches else None

    def _delivery(self, marker, rule):
        if rule is None:
            return None
        rule_id = rule["id"]
        runs = self._get(f"{self._wakeup_path}/{rule_id}/runs", list)
        if not runs:
            return None
        if len(runs) != 1 or not isinstance(runs[0], dict):
            raise NativeSourceError("ambiguous_wakeup_run")
        run = runs[0]
        run_id = _id(run.get("id"), "wakeup_run_id")
        if rule.get("last_task_id") != run_id:
            return None  # The rule and Run endpoints can straddle the scheduler commit.
        started = run.get("started_at")
        if started is None:
            return None
        created = _time(run.get("created_at"))
        if not (_time(rule["created_at"]) <= created <= _time(rule["expires_at"]) and created <= _time(started)):
            raise NativeSourceError("invalid_wakeup_run_time")
        exact = self._issue_runs().get(run_id)
        if (exact is None or exact.get("agent_id") != self._coordinator
                or exact.get("started_at") is None or _time(exact["started_at"]) != _time(started)):
            raise NativeSourceError("wakeup_run_scope_unconfirmed")
        return {
            **self._scope, "marker": marker, "kind": "issue_wakeup", "state": "started",
            "wakeup_id": rule_id, "run_id": run_id, "started_at": started,
        }

    def lookup(self, marker) -> dict | None:
        """Read reconciliation evidence without scheduling, including after restart."""
        instruction = self._instruction(marker)
        with self._lock:
            self._bind()
            rules = self._wakeup_rows()
            return self._delivery(marker, self._matching_wakeup(marker, instruction, rules))

    def _current_send_view(self):
        if not self._enabled:
            raise NativeSourceError("notifications_disabled")
        if self._poll_basis is None:
            raise NativeSourceError("verified_poll_required")
        issue = self._bind()
        _, summary_source, snapshot = self._summary(self._thread_rows())
        if (summary_source, snapshot, issue["status"]) != self._poll_basis:
            raise NativeSourceError("poll_snapshot_changed")
        return issue, self._wakeup_rows()

    def _require_ready(self, issue, rules):
        if issue["status"] in {"cancelled", "done", "paused"}:
            raise NativeSourceError("issue_closed_or_paused")
        catalog = self._get("/api/issue-statuses", dict).get("statuses")
        if not isinstance(catalog, list) or any(
            not isinstance(row, dict) or row.get("workspace_id") != self._workspace for row in catalog
        ):
            raise NativeSourceError("status_catalog_unconfirmed")
        categories = [row.get("category") for row in catalog if row.get("key") == issue["status"]]
        if len(categories) != 1 or categories[0] not in (*_OPEN_ISSUE_CATEGORIES, *_TERMINAL_ISSUE_CATEGORIES):
            raise NativeSourceError("issue_status_unconfirmed")
        if categories[0] in _TERMINAL_ISSUE_CATEGORIES:
            raise NativeSourceError("issue_closed_or_paused")
        for existing in rules:
            if (existing.get("agent_id") == self._coordinator
                    and existing.get("parent_comment_id") in (self._thread, None)
                    and (existing["enabled"] or existing.get("last_task_status") in _IN_FLIGHT)):
                raise NativeSourceError("coordinator_wakeup_already_active")
        if any(run["status"] in _IN_FLIGHT for run in self._issue_runs().values()):
            raise NativeSourceError("issue_run_in_flight")

    def check_ready(self) -> str | None:
        """Read-only before claiming a new send. Return None or a fixed hold reason."""
        with self._lock:
            try:
                self._require_ready(*self._current_send_view())
            except NativeSourceError as exc:
                return exc.code
            return None

    def notify(self, marker) -> dict | None:
        """Schedule at most one short-lived rule after the caller commits its claim."""
        instruction = self._instruction(marker)
        with self._lock:
            issue, rules = self._current_send_view()
            rule = self._matching_wakeup(marker, instruction, rules)
            checkpoint = self._poll_basis[1]["checkpoint_id"]
            if rule is not None or checkpoint in self._attempted:
                return self._delivery(marker, rule)
            self._require_ready(issue, rules)
            self._attempted.add(checkpoint)
            self._request("POST", self._wakeup_path, body={
                "agent_id": self._coordinator, "parent_comment_id": self._thread,
                "instruction": instruction, "kind": "event", "mode": "once",
                "condition": {"type": "issue_field", "field": "status", "value": issue["status"]},
                "expires_in_seconds": 60, "on_timeout": "end",
            })
            rules = self._wakeup_rows()
            return self._delivery(marker, self._matching_wakeup(marker, instruction, rules))
