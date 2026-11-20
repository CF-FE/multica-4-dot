"""v0.11.0 native workspace, project, Issue and Run operations for an authorized gateway."""

from __future__ import annotations

from datetime import date
import sqlite3
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, UUID, uuid5

from .action_journal import ActionConflict, ActionJournal
from .native_http import NativeHTTP, NativeHTTPError


def _enum(*values):
    return {"enum": list(values)}


_UUID = {"type": "string", "format": "uuid"}
_NULLABLE_UUID = {"type": ["string", "null"], "format": "uuid"}
_TEXT = {"type": "string", "minLength": 1}
_BOOLEAN = {"type": "boolean"}
_PRIORITY = _enum("urgent", "high", "medium", "low", "none")
_DATE = {"type": ["string", "null"], "format": "date"}
_REVISION = {"type": "integer", "minimum": 1, "maximum": 2**63 - 1}
_ACTIVE = {"queued", "dispatched", "running", "waiting_local_directory"}
_TERMINAL = {"completed", "failed", "cancelled"}
_PROJECT_FIELDS = {
    "title": _TEXT,
    "priority": _PRIORITY,
    "due_date": _DATE,
    "lead_type": _enum("agent", "member", None),
    "lead_id": _NULLABLE_UUID,
}


def _tool(name, description, *, read_only=False, required=(), **fields):
    properties = {"workspace_id": _UUID, **fields}
    keys = ["workspace_id", *required]
    if not read_only:
        properties["request_id"] = {**_UUID, "description": "Stable UUID reused for the same request."}
        keys.append("request_id")
    return {"name": name, "description": description, "readOnly": read_only, "inputSchema": {
        "type": "object", "properties": properties, "required": keys, "additionalProperties": False,
    }}


OPERATION_TOOLS = [
    _tool("get_workspace", "Read one configured Multica workspace.", read_only=True),
    _tool("list_projects", "List a bounded page of visible projects in one workspace.", read_only=True,
          limit={"type": "integer", "minimum": 1, "maximum": 100},
          offset={"type": "integer", "minimum": 0, "maximum": 1_000_000}),
    _tool("get_coordinator", "Read this workspace's configured coordinator and verify its native Agent.", read_only=True),
    _tool("create_project", "Create a workspace-visible project with optional priority, deadline and lead.",
          required=("title",), **_PROJECT_FIELDS),
    _tool("update_project", "Update project title, priority, deadline or a workspace-visible project's lead.",
          required=("project_id",), project_id=_UUID, **_PROJECT_FIELDS),
    _tool("update_issue", "Update priority, deadline or assignee. An Agent/Squad assignment can start a Run when start_run is true.",
          required=("project_id", "issue_id"), project_id=_UUID, issue_id=_UUID, expected_revision=_REVISION,
          priority=_PRIORITY, due_date=_DATE, assignee_type=_enum("agent", "member", "squad", None),
          assignee_id=_NULLABLE_UUID, start_run=_BOOLEAN),
    _tool("add_issue_note", "Save a top-level /note that suppresses agent triggering.",
          required=("project_id", "issue_id", "content"), project_id=_UUID, issue_id=_UUID, content=_TEXT),
    _tool("steer_run", "Submit a supplement to the exact running Run. Its native support and delivery state apply.",
          required=("project_id", "issue_id", "run_id", "content"),
          project_id=_UUID, issue_id=_UUID, run_id=_UUID, content=_TEXT),
    _tool("request_review", "Send a completed Run for the Issue workflow's in_review handoff. It can assign a reviewer and start their Run.",
          required=("project_id", "issue_id", "run_id"), project_id=_UUID, issue_id=_UUID, run_id=_UUID,
          expected_revision=_REVISION),
    _tool("cancel_run", "Cancel the exact in-flight Run on this Issue; pre-existing effects may remain.",
          required=("project_id", "issue_id", "run_id"), project_id=_UUID, issue_id=_UUID, run_id=_UUID),
    _tool("rerun_run", "Create a new Run from the exact source Run. Multica may replace pending Runs in the same thread.",
          required=("project_id", "issue_id", "run_id"), project_id=_UUID, issue_id=_UUID, run_id=_UUID, fresh=_BOOLEAN),
]
_TOOLS_BY_NAME = {tool["name"]: tool for tool in OPERATION_TOOLS}


class NativeOperationError(ValueError):
    """An input, scope, or evidence error with a stable diagnostic code."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _uuid(value, error="native_schema_drift"):
    if isinstance(value, str):
        try:
            canonical = str(UUID(value))
            if value.lower() == canonical:
                return canonical
        except ValueError:
            pass
    raise NativeOperationError(error)


def _object(value):
    if not isinstance(value, dict):
        raise NativeOperationError("native_schema_drift")
    return value


def _array(value):
    if not isinstance(value, list):
        raise NativeOperationError("native_schema_drift")
    return value


def _scope(row, **ids):
    for field, expected in ids.items():
        if row.get(field) is None or _uuid(row[field]) != expected:
            raise NativeOperationError("scope_mismatch")


def _text(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NativeOperationError("native_schema_drift")
    return value


def _revision(row):
    value = row.get("revision")
    if type(value) is not int or value < 1:
        raise NativeOperationError("native_schema_drift")
    return value


def _arguments(schema, arguments):
    fields = schema["properties"]
    if (not isinstance(arguments, dict) or arguments.keys() - fields.keys()
            or not set(schema["required"]).issubset(arguments)):
        raise NativeOperationError("invalid_arguments")
    normalized = {}
    for name, value in arguments.items():
        field = fields[name]
        if value is None and field.get("type") == ["string", "null"]:
            pass
        elif field.get("format") == "uuid":
            value = _uuid(value, "invalid_arguments")
        elif field.get("format") == "date":
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except (TypeError, ValueError):
                raise NativeOperationError("invalid_arguments") from None
        elif "enum" in field:
            if value not in field["enum"]:
                raise NativeOperationError("invalid_arguments")
        elif field["type"] == "integer":
            if type(value) is not int or not field["minimum"] <= value <= field["maximum"]:
                raise NativeOperationError("invalid_arguments")
        elif field["type"] == "boolean":
            if type(value) is not bool:
                raise NativeOperationError("invalid_arguments")
        elif not isinstance(value, str) or not value.strip() or "\0" in value:
            raise NativeOperationError("invalid_arguments")
        normalized[name] = value.strip() if name == "title" else value
    return normalized


def _pair(args, actor):
    type_key, id_key = actor + "_type", actor + "_id"
    if (type_key in args) != (id_key in args) or (args.get(type_key) is None) != (args.get(id_key) is None):
        raise NativeOperationError("invalid_actor_pair")
    return {key: args[key] for key in (type_key, id_key) if key in args}


class NativeOperations:
    """Requires caller authentication and workspace authorization in the gateway.

    coordinator_ids is an optional trusted workspace-to-Agent registration. Each
    native receipt records immediate action evidence, without inferring a later Run or business outcome.
    """

    def __init__(self, http: NativeHTTP, *, instance_id, expected_user_id, state_path, coordinator_ids=None):
        if not isinstance(instance_id, str) or not instance_id.strip() or instance_id.strip() != instance_id:
            raise NativeOperationError("invalid_configuration")
        self._http = http
        self._instance_id = instance_id
        self._expected_user_id = _uuid(expected_user_id, "invalid_configuration")
        self._coordinators = {
            _uuid(workspace, "invalid_configuration"): _uuid(agent, "invalid_configuration")
            for workspace, agent in (coordinator_ids or {}).items()
        }
        self._journal = ActionJournal(state_path)

    def _get(self, path, workspace_id=None):
        return self._http.request("GET", path, workspace_id=workspace_id)

    def _workspace(self, workspace_id):
        row = _object(self._get(f"/api/workspaces/{workspace_id}"))
        _scope(row, id=workspace_id)
        return {"workspace_id": workspace_id, "name": _text(row, "name"), "slug": _text(row, "slug")}

    def _project(self, workspace_id, project_id):
        row = _object(self._get(f"/api/projects/{project_id}", workspace_id))
        _scope(row, id=project_id, workspace_id=workspace_id)
        return row

    def _issue(self, workspace_id, project_id, issue_id):
        row = _object(self._get(f"/api/issues/{issue_id}", workspace_id))
        _scope(row, id=issue_id, workspace_id=workspace_id, project_id=project_id)
        return row

    def _agent(self, workspace_id, agent_id):
        row = _object(self._get(f"/api/agents/{agent_id}", workspace_id))
        _scope(row, id=agent_id, workspace_id=workspace_id)
        if "archived_at" not in row or row["archived_at"] is not None:
            raise NativeOperationError("agent_unavailable")
        return row

    def _verify_actor(self, workspace_id, actor, actor_id):
        if actor == "agent":
            self._agent(workspace_id, actor_id)
        elif actor == "squad":
            row = _object(self._get(f"/api/squads/{actor_id}", workspace_id))
            _scope(row, id=actor_id, workspace_id=workspace_id)
            if "archived_at" not in row or row["archived_at"] is not None:
                raise NativeOperationError("squad_unavailable")
        elif actor == "member":
            rows = _array(self._get(f"/api/workspaces/{workspace_id}/members"))
            matches = [row for row in rows if _object(row).get("user_id") == actor_id]
            if len(matches) != 1:
                raise NativeOperationError("member_not_verified")
            _scope(matches[0], workspace_id=workspace_id, user_id=actor_id)

    def _read_action(self, action, workspace_id, args):
        if action == "get_workspace":
            return self._workspace(workspace_id)
        if action == "get_coordinator":
            coordinator_id = self._coordinators.get(workspace_id)
            if coordinator_id is None:
                raise NativeOperationError("coordinator_not_registered")
            row = self._agent(workspace_id, coordinator_id)
            runtime = row.get("runtime_id")
            if not isinstance(runtime, str):
                raise NativeOperationError("native_schema_drift")
            system_key = row.get("system_key")
            if system_key is not None and not isinstance(system_key, str):
                raise NativeOperationError("native_schema_drift")
            return {"workspace_id": workspace_id, "agent_id": coordinator_id, "name": _text(row, "name"),
                    "status": _text(row, "status"), "system_key": system_key,
                    "runtime_id": _uuid(runtime) if runtime else None}
        limit, offset = args.get("limit", 50), args.get("offset", 0)
        query = urlencode({"limit": limit, "offset": offset})
        page = _object(self._get(f"/api/projects?{query}", workspace_id))
        projects = []
        for row in _array(page.get("projects")):
            _scope(_object(row), workspace_id=workspace_id)
            lead_type, lead_id = row.get("lead_type"), row.get("lead_id")
            if ((lead_type is None) != (lead_id is None) or lead_type not in (None, "agent", "member")):
                raise NativeOperationError("project_lead_unverified")
            projects.append({"project_id": _uuid(row.get("id")), "title": _text(row, "title"),
                             "status": _text(row, "status"), "lead_type": lead_type,
                             "lead_id": _uuid(lead_id) if lead_id is not None else None})
        total, more = page.get("total"), page.get("has_more")
        if (type(total) is not int or total < 0 or type(more) is not bool or len(projects) > limit
                or len({row["project_id"] for row in projects}) != len(projects)
                or len(projects) != min(limit, max(0, total - offset)) or more != (offset + len(projects) < total)):
            raise NativeOperationError("native_schema_drift")
        return {"workspace_id": workspace_id, "projects": projects, "total": total,
                "next_offset": offset + len(projects) if more else None}

    def _run(self, workspace_id, project_id, issue_id, run_id):
        rows = _array(self._get(f"/api/issues/{issue_id}/task-runs?scope=issue&view=timeline", workspace_id))
        matches = [row for row in rows if _object(row).get("id") == run_id]
        if len(matches) != 1:
            raise NativeOperationError("exact_run_not_verified")
        row = matches[0]
        _scope(row, id=run_id, workspace_id=workspace_id, issue_id=issue_id)
        if "project_id" in row:
            _scope(row, project_id=project_id)
        if row.get("restricted", False) is not False:
            raise NativeOperationError("restricted_run")
        return row

    def call(self, principal: str, action: str, arguments: dict) -> dict:
        if not isinstance(principal, str) or not principal.strip():
            raise NativeOperationError("invalid_principal")
        tool = _TOOLS_BY_NAME.get(action)
        if tool is None:
            raise NativeOperationError("unknown_action")
        args = _arguments(tool["inputSchema"], arguments)
        me = _object(self._get("/api/me"))
        if _uuid(me.get("id")) != self._expected_user_id:
            raise NativeOperationError("identity_mismatch")
        ws = args["workspace_id"]
        if tool["readOnly"]:
            return {"instance_id": self._instance_id, **self._read_action(action, ws, args)}

        request_id = args.pop("request_id")
        if action == "rerun_run":
            args.setdefault("fresh", False)
        if action == "update_issue":
            args.setdefault("start_run", False)
        fingerprint = self._journal.fingerprint(self._instance_id, action, args)
        project_id, issue_id = args.get("project_id"), args.get("issue_id")
        receipt_scope = {"workspace_id": ws}
        project, issue = None, None
        if project_id is None:
            self._workspace(ws)
        else:
            project = self._project(ws, project_id)
            receipt_scope["project_id"] = project_id
        if issue_id is not None:
            issue = self._issue(ws, project_id, issue_id)
            receipt_scope["issue_id"] = issue_id
        if "run_id" in args:
            receipt_scope["run_id"] = args["run_id"]

        def report(result):
            return {"request_id": request_id, "action": action, "instance_id": self._instance_id,
                    **receipt_scope, **result}

        try:
            previous = self._journal.get(principal, request_id, fingerprint)
            if previous is None:
                method, path, body, verify = self._prepare(action, args, project, issue, principal, request_id)
                previous = self._journal.claim(principal, request_id, fingerprint)
            if previous is not None:
                if action == "create_project" and previous["status"] == "confirmed":
                    self._project(ws, previous["receipt"]["project_id"])
                return report(previous)
        except ActionConflict:
            raise NativeOperationError("request_conflict") from None

        try:
            reply = _object(self._http.request(method, path, workspace_id=ws, body=body))
            receipt = verify(reply)
            result = {"status": "confirmed", "receipt": receipt}
        except NativeHTTPError as exc:
            result = {"status": "unknown", "reason": exc.code}
            if exc.http_status is not None:
                result["http_status"] = exc.http_status
        except NativeOperationError as exc:
            result = {"status": "unknown", "reason": exc.code}
        try:
            self._journal.finish(principal, request_id, fingerprint, result)
        except sqlite3.Error:
            return report({"status": "unknown", "reason": "receipt_not_persisted"})
        return report(result)

    def _prepare(self, action, args, project, issue, principal, request_id):
        ws, project_id = args["workspace_id"], args.get("project_id")
        if action in {"create_project", "update_project"}:
            creating = action == "create_project"
            body = {key: args[key] for key in ("title", "priority", "due_date") if key in args}
            lead = _pair(args, "lead")
            if lead and not creating and project.get("visibility") != "workspace":
                raise NativeOperationError("project_lead_access_management")
            if lead:
                self._verify_actor(ws, lead["lead_type"], lead["lead_id"])
                body.update(lead)
            if not body:
                raise NativeOperationError("empty_update")
            if creating:
                body["visibility"] = "workspace"

            def verify(row):
                _scope(row, workspace_id=ws)
                native_id = _uuid(row.get("id"))
                if not creating and native_id != project_id:
                    raise NativeOperationError("scope_mismatch")
                _verify_fields(row, body)
                return {"project_id": native_id, "observed_fields": body}

            return ("POST", "/api/projects", body, verify) if creating else ("PUT", f"/api/projects/{project_id}", body, verify)

        issue_id = args["issue_id"]
        issue_path = f"/api/issues/{issue_id}"
        if action == "update_issue":
            body = {key: args[key] for key in ("priority", "due_date") if key in args}
            assignee = _pair(args, "assignee")
            if assignee:
                self._verify_actor(ws, assignee["assignee_type"], assignee["assignee_id"])
                body.update(assignee)
            if not body or (args["start_run"] and assignee.get("assignee_type") not in {"agent", "squad"}):
                raise NativeOperationError("invalid_issue_update")
            body["suppress_run"] = not args["start_run"]
            return self._issue_update(ws, project_id, issue_id, issue, args, body)

        if action == "add_issue_note":
            note = "/note " + args["content"]
            _check_content(note)

            def verify(row):
                receipt = self._comment_receipt(row, ws, project_id, issue_id, note)
                if row.get("trigger_outcomes") not in (None, []) or row.get("supplements") not in (None, []):
                    raise NativeOperationError("unexpected_note_effect")
                return {**receipt, "trigger_policy": "suppressed"}

            return "POST", issue_path + "/comments", {"type": "comment", "content": note}, verify

        run_id = args["run_id"]
        run = self._run(ws, project_id, issue_id, run_id)
        status = _text(run, "status")
        source_agent = _uuid(run.get("agent_id"))
        if action == "steer_run":
            if status != "running" or run.get("can_supplement") is not True:
                raise NativeOperationError("run_supplement_unavailable")
            content = args["content"]
            _check_content(content)
            client_key = str(uuid5(NAMESPACE_URL, repr(("multica-mcp-steer-v1", self._instance_id, principal, request_id))))

            def verify(row):
                receipt = self._comment_receipt(row, ws, project_id, issue_id, content)
                supplements = _array(row.get("supplements"))
                if len(supplements) != 1 or row.get("trigger_outcomes") not in (None, []):
                    raise NativeOperationError("supplement_receipt_unverified")
                supplement = _object(supplements[0])
                _scope(supplement, task_id=run_id, agent_id=source_agent)
                return {**receipt, "run_id": run_id, "supplement_status": _text(supplement, "status"),
                        "delivered_at": supplement.get("delivered_at")}

            return "POST", f"{issue_path}/tasks/{run_id}/supplements", {
                "content": content, "client_request_id": client_key,
            }, verify

        if action == "request_review":
            if status != "completed":
                raise NativeOperationError("review_candidate_not_completed")
            preview = _object(self._get(issue_path + "/workflow-handoff?status=in_review", ws))
            if preview.get("from_status") != _text(issue, "status") or preview.get("to_status") != "in_review":
                raise NativeOperationError("workflow_preview_mismatch")
            reviewer_type = preview.get("handler_type")
            if preview.get("handoff") is not True or reviewer_type not in ("agent", "member"):
                raise NativeOperationError("review_handoff_unconfigured")
            reviewer_id = _uuid(preview.get("handler_id"))
            if reviewer_id == source_agent:
                raise NativeOperationError("reviewer_is_source_agent")
            self._verify_actor(ws, reviewer_type, reviewer_id)
            expected = {"assignee_type": reviewer_type, "assignee_id": reviewer_id}
            return self._issue_update(ws, project_id, issue_id, issue, args, {"status": "in_review"}, expected)

        cancelling = action == "cancel_run"
        if cancelling and status not in _ACTIVE:
            raise NativeOperationError("run_not_in_flight")
        if not cancelling and status not in _ACTIVE | _TERMINAL:
            raise NativeOperationError("run_state_unverified")

        def verify(row):
            _scope(row, workspace_id=ws, issue_id=issue_id, agent_id=source_agent)
            if "project_id" in row:
                _scope(row, project_id=project_id)
            native_run_id = _uuid(row.get("id"))
            native_status = _text(row, "status")
            if cancelling:
                actor = row.get("cancelled_by")
                if (native_run_id != run_id or native_status != "cancelled" or not isinstance(actor, dict)
                        or actor.get("type") != "member" or actor.get("id") != self._expected_user_id):
                    raise NativeOperationError("cancellation_receipt_unverified")
            elif native_run_id == run_id or _object(row.get("attribution")).get("rerun_of_task_id") != run_id:
                raise NativeOperationError("rerun_receipt_unverified")
            self._issue(ws, project_id, issue_id)
            return {"run_id": native_run_id, "source_run_id": run_id, "run_status": native_status}

        if cancelling:
            return "POST", f"{issue_path}/tasks/{run_id}/cancel", {}, verify
        return "POST", f"/api/tasks/{run_id}/rerun", {"fresh": args["fresh"]}, verify

    def _issue_update(self, ws, project_id, issue_id, issue, args, body, expected=None):
        revision = _revision(issue)
        if args.get("expected_revision", revision) != revision:
            raise NativeOperationError("issue_revision_conflict")
        fields = {key: value for key, value in body.items() if key != "suppress_run"}
        if expected is not None:
            fields.update(expected)

        def verify(row):
            _scope(row, id=issue_id, workspace_id=ws, project_id=project_id)
            _verify_fields(row, fields)
            native_revision = _revision(row)
            if native_revision <= revision:
                raise NativeOperationError("issue_revision_unconfirmed")
            outcome = _run_outcome(row)
            if body.get("suppress_run") is True and outcome is not None and outcome["status"] == "queued":
                raise NativeOperationError("unexpected_automatic_run")
            return {"issue_id": issue_id, "revision": native_revision, "observed_fields": fields,
                    "run_outcome": outcome}

        return "PUT", f"/api/issues/{issue_id}", {**body, "expected_revision": revision}, verify

    def _comment_receipt(self, row, ws, project_id, issue_id, content):
        _scope(row, issue_id=issue_id, author_id=self._expected_user_id)
        _verify_fields(row, {"author_type": "member", "content": content, "parent_id": None, "type": "comment"})
        self._issue(ws, project_id, issue_id)
        return {"comment_id": _uuid(row.get("id")), "issue_id": issue_id}


def _check_content(value):
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise NativeOperationError("invalid_content") from None
    if size > 64 * 1024:
        raise NativeOperationError("invalid_content")


def _verify_fields(row, fields):
    if any(key not in row or row[key] != value for key, value in fields.items()):
        raise NativeOperationError("native_receipt_mismatch")


def _run_outcome(row):
    outcome = row.get("run_outcome")
    if outcome is None:
        return None
    outcome = _object(outcome)
    status, target_type = _text(outcome, "status"), _text(outcome, "target_type")
    target_id = _uuid(outcome.get("target_id"))
    if (status not in {"queued", "coalesced", "deferred", "blocked"} or target_type not in {"agent", "squad"}
            or target_type != row.get("assignee_type") or target_id != row.get("assignee_id")):
        raise NativeOperationError("run_outcome_unverified")
    return {"status": status, "reason_code": _text(outcome, "reason_code"), "target_id": target_id,
            "target_type": target_type}
