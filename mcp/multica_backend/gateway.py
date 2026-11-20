"""Dot's typed business operations over a fixed directory of enrolled Multica instances."""

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker

from .action_journal import ActionConflict
from .delivery import DeliveryLedger, DispatchCommand, NewIssue, RequestConflict, UnverifiedIssue
from .mailbox import Mailbox, MailboxError
from .multica_api import MulticaAPI, MulticaAPIError, _parse_origin
from .native_dispatch import MulticaDispatch
from .native_http import NativeHTTP
from .native_operations import NativeOperations, NativeOperationError, OPERATION_TOOLS


class GatewayError(ValueError):
    """Machine-readable gateway error, without native content or credential material."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _text(limit=256):
    return {"type": "string", "minLength": 1, "maxLength": limit}


_ID = {**_text(36), "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"}
_SCOPE = {"instance_id": _text(), "workspace_id": _ID, "project_id": _ID}
_REQUEST = {"request_id": _text()}


def _schema(fields, *required):
    return {"type": "object", "properties": fields, "required": list(required), "additionalProperties": False}


def _tool(name, description, schema, *, read=True):
    return {"name": name, "description": description, "readOnly": read, "inputSchema": schema}


_NEW = {"title": _text(512), "status": _text(128), "description": _text(32768)}
_MAIL = _schema({"job_id": _text(), "payload_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"}},
                "job_id", "payload_hash")
_DISPATCH = _schema({**_SCOPE, **_REQUEST, "new_issue": _schema(_NEW, "title", "status"),
                     "original_issue_id": _ID, "mailbox": _MAIL}, *_SCOPE, "request_id")
_DISPATCH["oneOf"] = [{"required": ["new_issue"]}, {"required": ["original_issue_id"]}]
_RECEIPT = {**_SCOPE, **_REQUEST}
TOOL_CATALOG = [
    _tool("list_instances", "List enrolled instances and workspaces accessible to this Dot identity.", _schema({})),
    _tool("get_project", "Read one native project within its verified workspace.", _schema(_SCOPE, *_SCOPE)),
    _tool("get_issue", "Read an Issue in its verified project.", _schema({**_SCOPE, "issue_id": _ID}, *_SCOPE, "issue_id")),
    _tool("list_issue_runs", "List the visible native Runs of one Issue.", _schema({**_SCOPE, "issue_id": _ID}, *_SCOPE, "issue_id")),
    _tool("get_run", "Read a specific Run of a verified Issue.", _schema({**_SCOPE, "issue_id": _ID, "run_id": _ID}, *_SCOPE, "issue_id", "run_id")),
    _tool("dispatch_issue", "Create and assign a project Issue, or link an existing Issue without starting it. Reuse the original request ID on retry.", _DISPATCH, read=False),
    _tool("get_dispatch", "Look up the authenticated caller's dispatch receipt.", _schema(_RECEIPT, *_RECEIPT)),
    _tool("get_dispatch_result", "Read a linked Mailbox result version and its read acknowledgement.", _schema({**_RECEIPT, "version": {"type":"integer", "minimum":1}}, *_RECEIPT, "version")),
]

# Native operation schemas own their arguments. The gateway owns instance selection.
for _entry in OPERATION_TOOLS:
    _operation = deepcopy(_entry)
    _inputs = _operation["inputSchema"]
    _inputs["properties"]["instance_id"] = _text()
    if "instance_id" not in _inputs["required"]:
        _inputs["required"].append("instance_id")
    TOOL_CATALOG.append(_operation)
_TOOLS = {tool["name"]: tool for tool in TOOL_CATALOG}
if len(_TOOLS) != len(TOOL_CATALOG):
    raise RuntimeError("duplicate MCP tool name")
_VALIDATORS = {name: Draft202012Validator(tool["inputSchema"], format_checker=FormatChecker())
               for name, tool in _TOOLS.items()}


@dataclass(frozen=True)
class Workspace:
    coordinator_id: str
    correlation_property_id: str | None
    mailbox_recipient: str | None
    mailbox_property_id: str | None = None
    legacy_mailbox_property_id: str | None = None


@dataclass(frozen=True, repr=False)
class Instance:
    origin: str
    expected_user_id: str
    token: str
    allow_private_http: bool
    principals: frozenset[str]
    workspaces: dict[str, Workspace]
    enabled_writes: frozenset[str]


def _names(values, field):
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f"invalid {field}")
    return frozenset(values)


def _instance(config):
    private_http = config.get("allow_private_http", False)
    if type(private_http) is not bool:
        raise ValueError("invalid allow_private_http")
    _parse_origin(config["origin"], private_http)
    env, credential = config.get("pat_env"), config.get("pat_credential")
    if bool(env) == bool(credential):
        raise ValueError("configure one PAT source per instance")
    if credential:
        if Path(credential).name != credential or credential in {".", ".."}:
            raise ValueError("invalid credential name")
        token = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / credential).read_text().strip()
    else:
        token = os.environ[env]
    if not token or any(not 33 <= ord(c) <= 126 for c in token):
        raise ValueError("invalid instance credential")
    workspaces = {}
    for key, ws in config["workspaces"].items():
        prop = ws.get("correlation_property_id")
        mail_prop = ws.get("mailbox_property_id")
        legacy_prop = ws.get("legacy_mailbox_property_id")
        workspaces[str(UUID(key))] = Workspace(str(UUID(ws["coordinator_id"])),
                                               str(UUID(prop)) if prop else None,
                                               ws.get("mailbox_recipient"),
                                               str(UUID(mail_prop)) if mail_prop else None,
                                               str(UUID(legacy_prop)) if legacy_prop else None)
    writes = _names(config.get("enabled_writes", []), "enabled_writes")
    if any(name not in _TOOLS or _TOOLS[name]["readOnly"] for name in writes):
        raise ValueError("unrecognized write capability")
    return Instance(config["origin"], str(UUID(config["expected_user_id"])), token, private_http,
                    _names(config["principals"], "principals"), workspaces, writes)


class Gateway:
    def __init__(self, instances: dict[str, Instance], state_dir: Path):
        self.instances = instances
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.ledger = DeliveryLedger(self.state_dir / "delivery.sqlite3")
        with closing(sqlite3.connect(self.ledger.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS gateway_request_tools (
                principal TEXT NOT NULL, request_id TEXT NOT NULL, tool TEXT NOT NULL,
                PRIMARY KEY(principal, request_id))""")

    @classmethod
    def from_env(cls):
        records = json.loads(Path(os.environ["MULTICA_MCP_CONFIG"]).read_text())["instances"]
        if not isinstance(records, dict) or not records:
            raise ValueError("at least one enrolled instance is required")
        return cls({key: _instance(value) for key, value in records.items()}, Path(os.environ["MULTICA_MCP_STATE_DIR"]))

    @staticmethod
    def _mailbox():
        return Mailbox.from_env()

    def _bind_tool(self, principal, request_id, name):
        # Both native write journals share this request-ID namespace.
        with closing(sqlite3.connect(self.ledger.path)) as db, db:
            db.execute("INSERT INTO gateway_request_tools VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                       (principal, request_id, name))
            row = db.execute("SELECT tool FROM gateway_request_tools WHERE principal=? AND request_id=?",
                             (principal, request_id)).fetchone()
            if row[0] != name:
                raise GatewayError("request_conflict")

    def _scope(self, principal, instance_id, workspace_id):
        instance = self.instances.get(instance_id)
        workspace = instance.workspaces.get(workspace_id) if instance else None
        if instance is None or principal not in instance.principals or workspace is None:
            raise GatewayError("scope_unavailable")
        return instance, workspace

    @staticmethod
    def _reader(instance, workspace_id, project_id):
        return MulticaAPI(origin=instance.origin, token=instance.token, expected_user_id=instance.expected_user_id,
                          workspace_id=workspace_id, project_id=project_id, allow_private_http=instance.allow_private_http)

    def _verify_link(self, command):
        if command.mailbox_job_id is not None:
            if not command.mailbox_payload_hash or not command.mailbox_recipient:
                raise GatewayError("original_job_binding_unverified")
            original = self._mailbox().verify_job(job_id=command.mailbox_job_id, payload_hash=command.mailbox_payload_hash,
                                                  workspace_id=command.workspace_id, project_id=command.project_id,
                                                  recipient=command.mailbox_recipient)
            if command.new_issue is not None and original["latest_result_version"] > 0:
                raise GatewayError("mailbox_job_already_reported")

    def _deliver(self, principal, request_id, command):
        instance, workspace = self._scope(principal, command.instance_id, command.workspace_id)
        if "dispatch_issue" not in instance.enabled_writes:
            raise GatewayError("write_capability_disabled")
        if command.coordinator_id != workspace.coordinator_id:
            raise GatewayError("coordinator_changed")
        if command.mailbox_recipient and command.mailbox_recipient != workspace.mailbox_recipient:
            raise GatewayError("mailbox_route_changed")
        current = self.ledger.get(principal, request_id)
        self._reader(instance, command.workspace_id, command.project_id).get_project()
        if current is not None and current.state == "confirmed":
            return asdict(self.ledger.accept(principal, request_id, command))
        if current is None or current.state == "accepted":
            self._verify_link(command)
        http = NativeHTTP(origin=instance.origin, token=instance.token, allow_private_http=instance.allow_private_http)
        markers = {"mailbox_property_id": workspace.mailbox_property_id}
        if workspace.legacy_mailbox_property_id:
            markers["legacy_mailbox_property_id"] = workspace.legacy_mailbox_property_id
        native = MulticaDispatch(http, instance_id=command.instance_id, expected_user_id=instance.expected_user_id,
                                 correlation_property_id=workspace.correlation_property_id, **markers)
        return asdict(self.ledger.deliver(principal, request_id, command, native))

    def call(self, principal: str, name: str, arguments: dict) -> dict:
        try:
            return self._call(principal, name, arguments)
        except (GatewayError, NativeOperationError) as exc:
            return {"error": {"code": exc.code}}
        except (RequestConflict, ActionConflict):
            return {"error": {"code": "request_conflict"}}
        except UnverifiedIssue:
            return {"error": {"code": "issue_evidence_unverified"}}
        except (MulticaAPIError, MailboxError) as exc:
            return {"error": {**exc.diagnostic(), "source": "task-mailbox" if isinstance(exc, MailboxError) else "multica"}}

    def _call(self, principal: str, name: str, arguments: dict) -> dict:
        if not isinstance(principal, str) or not principal.strip():
            raise GatewayError("unauthenticated")
        if name not in _TOOLS:
            raise GatewayError("unknown_tool")
        if not _VALIDATORS[name].is_valid(arguments):
            raise GatewayError("invalid_arguments")
        if name == "list_instances":
            return {"instances": [{"instance_id": key, "workspace_ids": sorted(inst.workspaces)}
                                  for key, inst in self.instances.items() if principal in inst.principals]}
        args = dict(arguments)
        instance_id = args.pop("instance_id")
        workspace_id = str(UUID(args["workspace_id"]))
        args["workspace_id"] = workspace_id
        instance, workspace = self._scope(principal, instance_id, workspace_id)
        project_id = str(UUID(args["project_id"])) if "project_id" in args else None
        if not _TOOLS[name]["readOnly"] and name not in instance.enabled_writes:
            raise GatewayError("write_capability_disabled")
        if not _TOOLS[name]["readOnly"]:
            self._bind_tool(principal, args["request_id"], name)
        if name in {"get_project", "get_issue", "list_issue_runs", "get_run"}:
            reader = self._reader(instance, workspace_id, project_id)
            if name == "list_issue_runs":
                return {"runs": [asdict(row) for row in reader.list_issue_runs(args["issue_id"])]}
            if name == "get_project":
                return asdict(reader.get_project())
            if name == "get_run":
                return asdict(reader.get_run(args["issue_id"], args["run_id"]))
            return asdict(reader.get_issue(args["issue_id"]))
        if name == "dispatch_issue":
            job = args.get("mailbox", {})
            raw = args.get("new_issue")
            if job and not workspace.mailbox_recipient:
                raise GatewayError("missing_mailbox_recipient")
            if raw and job:
                route = json.dumps({"job_id": job["job_id"], "payload_hash": job["payload_hash"],
                                    "report_route": "task-mailbox:original-job"}, ensure_ascii=False)
                raw = dict(raw, description=raw.get("description", "") +
                           "\n\n原信箱委托（核读原件，在原 job 回报）\n" + route)
            command = DispatchCommand(instance_id, workspace_id, project_id, workspace.coordinator_id,
                                      NewIssue(**raw) if raw else None, args.get("original_issue_id"),
                                      project_id if job else None, job.get("job_id"), job.get("payload_hash"),
                                      workspace.mailbox_recipient if job else None)
            return self._deliver(principal, args["request_id"], command)
        if name in {"get_dispatch", "get_dispatch_result"}:
            request = args["request_id"]
            receipt = self.ledger.get(principal, request)
            if receipt is None or (receipt.instance_id, receipt.workspace_id, receipt.project_id) != (
                instance_id, workspace_id, project_id
            ):
                raise GatewayError("dispatch_unavailable")
            self._reader(instance, workspace_id, project_id).get_project()
            if name == "get_dispatch":
                return asdict(receipt)
            link = self.ledger.mailbox_link(principal, request)
            if link is None:
                raise GatewayError("dispatch_has_no_mailbox")
            return self._mailbox().receipt(job_id=link["job_id"], version=args["version"])
        http = NativeHTTP(origin=instance.origin, token=instance.token, allow_private_http=instance.allow_private_http)
        operations = NativeOperations(http, instance_id=instance_id, expected_user_id=instance.expected_user_id,
                                      state_path=self.state_dir / "actions.sqlite3",
                                      coordinator_ids={workspace_id: workspace.coordinator_id})
        return operations.call(principal, name, args)

    def recover(self, authorized_writers):
        """Resume frozen commands only for currently authorized principals; uncertain sends only reconcile."""
        totals = {"checked": 0, "confirmed": 0, "pending": 0, "errors": 0}
        enrolled = set().union(*(instance.principals for instance in self.instances.values()))
        for principal in sorted(enrolled.intersection(authorized_writers)):
            # Visit unknown before accepted so an inconclusive new send is not immediately retried.
            for state in ("unknown", "accepted"):
                cursor = ""
                while page := self.ledger.list_pending(principal, state=state, after_request_id=cursor):
                    for request_id in page:
                        command = self.ledger.get_command(principal, request_id)
                        if command is None:
                            continue
                        totals["checked"] += 1
                        try:
                            receipt = self._deliver(principal, request_id, command)
                        except (GatewayError, MulticaAPIError, UnverifiedIssue, RequestConflict, MailboxError):
                            totals["errors"] += 1
                        else:
                            totals["confirmed" if receipt["state"] == "confirmed" else "pending"] += 1
                    cursor = page[-1]
        return totals
