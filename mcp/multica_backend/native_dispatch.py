"""Native Issue dispatch against the v0.11.0 API."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlencode

from .delivery import DispatchCommand, HistoricalIssueUnverified, IssueReference, UnverifiedIssue
from .multica_api import _match_id, _uuid
from .native_http import NativeHTTP, NativeHTTPError
from .native_intake import read_intake_run, read_receipt


_PAGE_SIZE = 25
_MAX_PAGES = 4
_CORRELATION = re.compile(r"mcp-dispatch-v1:[0-9a-f]{64}")
_LEGACY_MAILBOX_METADATA = "task_mailbox_job_id"


def _object(value: Any, check: str) -> dict:
    if not isinstance(value, dict):
        raise NativeHTTPError(check, "schema_drift")
    return value


def _rows(obj: dict, field: str, check: str) -> list[dict]:
    records = obj.get(field)
    if not isinstance(records, list):
        raise NativeHTTPError(check, "schema_drift", field=field)
    return [_object(row, check) for row in records]


def _check_total(obj: dict, expected: int, check: str, *, field: str = "total") -> None:
    if type(obj.get(field)) is not int or obj[field] != expected:
        raise NativeHTTPError(check, "schema_drift", field=field)


def _require_active(obj: dict, check: str) -> None:
    if "archived_at" not in obj:
        raise NativeHTTPError(check, "schema_drift", field="archived_at")
    if obj["archived_at"] is not None:
        raise NativeHTTPError(check, "archived")


class MulticaDispatch:
    """Bind dispatch to one configured origin and one known Multica account.

    The caller checks current G8 authority and the coordinator appointment.
    This adapter then verifies the native identity, route and invocation preview.
    The optional legacy property is only read, and never serves as a write key.
    """

    def __init__(
        self, http: NativeHTTP, *, instance_id: str, expected_user_id: str,
        correlation_property_id: str | None, mailbox_property_id: str | None = None,
        legacy_mailbox_property_id: str | None = None,
    ) -> None:
        if not isinstance(instance_id, str) or not instance_id or instance_id != instance_id.strip():
            raise NativeHTTPError("configuration", "invalid_input", field="instance_id")
        self._http = http
        self._instance_id = instance_id
        self._user_id = _uuid(expected_user_id, "configuration", "expected_user_id")
        properties = {
            key: _uuid(value, "configuration", key) if value is not None else None
            for key, value in {
                "correlation_property_id": correlation_property_id, "mailbox_property_id": mailbox_property_id,
                "legacy_mailbox_property_id": legacy_mailbox_property_id,
            }.items()
        }
        self._correlation_property_id = properties["correlation_property_id"]
        self._mailbox_property_id = properties["mailbox_property_id"]
        self._legacy_mailbox_property_id = properties["legacy_mailbox_property_id"]
        configured = [value for value in properties.values() if value is not None]
        if len(configured) != len(set(configured)):
            raise NativeHTTPError("configuration", "duplicate_dispatch_properties")

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def _handle_scope(self, command: DispatchCommand) -> dict:
        if command.instance_id != self.instance_id:
            raise UnverifiedIssue("native adapter does not match the requested instance")
        identity = _object(self._http.request("GET", "/api/me"), "identity")
        _match_id(identity, "id", self._user_id, "identity")
        project = self._get(command, f"/api/projects/{command.project_id}", "project")
        _match_id(project, "id", command.project_id, "project")
        _match_id(project, "workspace_id", command.workspace_id, "project")
        return project

    def _get(self, command: DispatchCommand, path: str, check: str) -> dict:
        return _object(self._http.request("GET", path, workspace_id=command.workspace_id), check)

    def _validate_text_property(self, command: DispatchCommand, property_id: str, *, writable: bool) -> None:
        prop = self._get(command, f"/api/properties/{property_id}", "property")
        _match_id(prop, "id", property_id, "property")
        _match_id(prop, "workspace_id", command.workspace_id, "property")
        if prop.get("type") != "text":
            raise NativeHTTPError("property", "incompatible_property_type")
        if type(prop.get("archived")) is not bool:
            raise NativeHTTPError("property", "schema_drift", field="archived")
        if writable and prop["archived"]:
            raise NativeHTTPError("property", "archived")

    def _mailbox_marker(self, command: DispatchCommand, *, writable: bool = False) -> dict[str, str]:
        if command.mailbox_job_id is None:
            return {}
        if command.mailbox_payload_hash is None:
            raise UnverifiedIssue("Mailbox job provenance has not been verified")
        if self._mailbox_property_id is None:
            if writable:
                raise NativeHTTPError("configuration", "missing_mailbox_property", field="mailbox_property_id")
            return {}
        ref = json.dumps([command.mailbox_project_id, command.mailbox_job_id], separators=(",", ":")).encode("utf-8")
        return {self._mailbox_property_id: "mcp-mailbox-v1:" + hashlib.sha256(ref).hexdigest()}

    def _verify_mailbox_reference(
        self, command: DispatchCommand, issue: dict, *, allow_legacy: bool = False,
    ) -> None:
        if command.mailbox_job_id is None:
            return
        current = self._mailbox_marker(command, writable=not allow_legacy)
        props = _object(issue.get("properties"), "issue")
        if current and all(props.get(key) == value for key, value in current.items()):
            return
        if allow_legacy:
            if self._legacy_mailbox_property_id and props.get(self._legacy_mailbox_property_id) == command.mailbox_job_id:
                return
            if _object(issue.get("metadata"), "issue").get(_LEGACY_MAILBOX_METADATA) == command.mailbox_job_id:
                return
        raise UnverifiedIssue("native Issue does not have the exact requested Mailbox reference")

    def _verified_issue(
        self, command: DispatchCommand, issue: dict, *,
        issue_id: str | None = None, expected_creator: bool = False,
    ) -> IssueReference:
        _match_id(issue, "workspace_id", command.workspace_id, "issue")
        _match_id(issue, "project_id", command.project_id, "issue")
        actual_id = _uuid(issue.get("id"), "issue", "id")
        if issue_id is not None and actual_id != issue_id:
            raise UnverifiedIssue("native Issue does not match the requested UUID")
        if expected_creator:
            _match_id(issue, "creator_id", self._user_id, "issue")
            if issue.get("creator_type") != "member":
                raise UnverifiedIssue("native Issue creator does not match the dispatch identity")
        return IssueReference(self.instance_id, command.workspace_id, command.project_id, actual_id)

    @staticmethod
    def _verify_marker(issue: dict, bag: str, key: str, value: str) -> None:
        if _object(issue.get(bag), "issue").get(key) != value:
            raise UnverifiedIssue("native Issue does not have the exact requested association")

    def _search_exact(
        self, command: DispatchCommand, key: str, value: str, *,
        bag: str = "properties", expected_creator: bool = False,
    ) -> tuple[IssueReference, dict] | None:
        if bag == "properties" and value == "__none__":
            raise NativeHTTPError("issue_lookup", "unrepresentable_legacy_marker")
        query = {
            "project_id": command.project_id,
            bag: json.dumps({key: [value] if bag == "properties" else value}, separators=(",", ":")),
            "sort": "created_at",
            "direction": "asc",
            "limit": _PAGE_SIZE,
        }
        total = None
        matches: set[str] = set()
        for page in range(_MAX_PAGES):
            offset = page * _PAGE_SIZE
            path = "/api/issues?" + urlencode(dict(query, offset=offset))
            result = self._get(command, path, "issue_lookup")
            issues = _rows(result, "issues", "issue_lookup")
            count = result.get("total")
            if type(count) is not int or count < 0:
                raise NativeHTTPError("issue_lookup", "schema_drift", field="total")
            if (total is not None and count != total) or len(issues) != min(_PAGE_SIZE, max(0, count - offset)):
                raise NativeHTTPError("issue_lookup", "incomplete_lookup")
            if count > _PAGE_SIZE * _MAX_PAGES:
                raise NativeHTTPError("issue_lookup", "page_limit")
            total = count
            for issue in issues:
                match = self._verified_issue(command, issue, expected_creator=expected_creator)
                self._verify_marker(issue, bag, key, value)
                if match.issue_id in matches:
                    raise NativeHTTPError("issue_lookup", "incomplete_lookup")
                matches.add(match.issue_id)
            if len(matches) == total:
                break
        if not matches:
            return None
        if len(matches) != 1:
            if not expected_creator:
                raise HistoricalIssueUnverified("historical_issue_ambiguous")
            raise UnverifiedIssue("native Issue association matches more than one Issue")
        issue_id = next(iter(matches))
        try:
            detail = self._get(command, f"/api/issues/{issue_id}", "issue")
            ref = self._verified_issue(command, detail, issue_id=issue_id, expected_creator=expected_creator)
            self._verify_marker(detail, bag, key, value)
        except (NativeHTTPError, UnverifiedIssue) as exc:
            if not expected_creator:
                raise HistoricalIssueUnverified("historical_issue_unverified", issue_id) from exc
            raise
        return ref, detail

    def lookup(self, command: DispatchCommand, correlation: str) -> IssueReference | None:
        self._handle_scope(command)
        if command.original_issue_id is not None:
            issue = self._get(command, f"/api/issues/{command.original_issue_id}", "issue")
            ref = self._verified_issue(command, issue, issue_id=command.original_issue_id)
            self._verify_mailbox_reference(command, issue, allow_legacy=True)
            return ref

        self._check_correlation(correlation)
        if self._correlation_property_id is not None:
            exact = self._search_exact(command, self._correlation_property_id, correlation, expected_creator=True)
            if exact is not None:
                reference, detail = exact
                self._validate_text_property(command, self._correlation_property_id, writable=False)
                self._verify_mailbox_reference(command, detail)
                return reference
        if command.mailbox_job_id is not None:
            association = self._find_mailbox_issue(command)
            if association is not None:
                prior, reason = association
                if self._read_receipt(command, prior)["state"] != "accepted":
                    raise HistoricalIssueUnverified(reason, prior.issue_id)
                return prior
        self._property_id()
        return None

    def _find_mailbox_issue(self, command: DispatchCommand) -> tuple[IssueReference, str] | None:
        # Historical jobs used the metadata bag. Check it before any property
        # provisioning requirement, including in workspaces with zero definitions.
        keys = [("metadata", _LEGACY_MAILBOX_METADATA, command.mailbox_job_id, "legacy_mailbox_issue_exists")]
        if self._legacy_mailbox_property_id:
            keys.append(("properties", self._legacy_mailbox_property_id, command.mailbox_job_id,
                         "legacy_mailbox_issue_exists"))
        keys.extend(("properties", key, value, "mailbox_issue_already_exists")
                    for key, value in self._mailbox_marker(command).items())
        candidate = None
        for bag, key, value, reason in keys:
            try:
                if bag == "properties":
                    self._validate_text_property(command, key, writable=False)
                found = self._search_exact(command, key, value, bag=bag)
            except HistoricalIssueUnverified:
                raise
            except UnverifiedIssue as exc:
                issue_id = candidate[0].issue_id if candidate else None
                raise HistoricalIssueUnverified("historical_issue_unverified", issue_id) from exc
            except NativeHTTPError as exc:
                if candidate is not None:
                    raise HistoricalIssueUnverified("historical_issue_unverified", candidate[0].issue_id) from exc
                raise
            if found is None:
                continue
            reference, _ = found
            if candidate is not None and reference != candidate[0]:
                raise HistoricalIssueUnverified("historical_issue_ambiguous")
            if candidate is None:
                candidate = reference, reason

        return candidate

    def _read_receipt(self, command: DispatchCommand, issue: IssueReference) -> dict:
        return read_receipt(self._http, issue, job_id=command.mailbox_job_id,
                            payload_hash=command.mailbox_payload_hash, coordinator_id=command.coordinator_id)

    def inspect_intake(self, command: DispatchCommand, issue: IssueReference, correlation: str) -> tuple[dict, dict]:
        try:
            detail = self._get(command, f"/api/issues/{issue.issue_id}", "issue")
            self._verified_issue(command, detail, issue_id=issue.issue_id)
            self._verify_mailbox_reference(command, detail, allow_legacy=True)
            association = self._find_mailbox_issue(command)
            if association is None or association[0] != issue:
                raise UnverifiedIssue("Mailbox association could not be confirmed")
        except HistoricalIssueUnverified as exc:
            return ({"state": "unconfirmed", "reason": exc.code}, {"state": "unconfirmed"})
        except (NativeHTTPError, UnverifiedIssue):
            return ({"state": "unconfirmed", "reason": "issue_evidence_unverified"}, {"state": "unconfirmed"})

        receipt = self._read_receipt(command, issue)
        properties = detail["properties"]
        if (self._correlation_property_id is None or properties.get(self._correlation_property_id) != correlation
                or detail.get("creator_type") != "member" or detail.get("creator_id") != self._user_id):
            return receipt, {"state": "unattributed"}
        return receipt, read_intake_run(self._http, issue, coordinator_id=command.coordinator_id,
                                       receipt=receipt.get("receipt", {}))

    def _property_id(self) -> str:
        if self._correlation_property_id is None:
            raise NativeHTTPError("configuration", "missing_dispatch_property", field="correlation_property_id")
        return self._correlation_property_id

    @staticmethod
    def _check_correlation(correlation: str) -> None:
        if not isinstance(correlation, str) or _CORRELATION.fullmatch(correlation) is None:
            raise NativeHTTPError("request", "invalid_input", field="correlation")

    @staticmethod
    def _assignee(command: DispatchCommand) -> dict[str, str]:
        if command.new_issue is None:
            raise NativeHTTPError("request", "invalid_input", field="new_issue")
        return {
            "project_id": command.project_id,
            "assignee_type": "agent",
            "assignee_id": command.coordinator_id,
            "status": command.new_issue.status,
        }

    def check_create(self, command: DispatchCommand) -> None:
        payload = self._assignee(command)
        project = self._handle_scope(command)
        _require_active(project, "project")
        agent = self._get(command, f"/api/agents/{command.coordinator_id}", "agent")
        _match_id(agent, "id", command.coordinator_id, "agent")
        _match_id(agent, "workspace_id", command.workspace_id, "agent")
        _require_active(agent, "agent")
        visibility = project.get("visibility")
        if visibility not in ("private", "workspace"):
            raise NativeHTTPError("project", "schema_drift", field="visibility")
        if visibility == "private":
            self._check_private_project(command, agent)
        self._check_status(command, project, payload["status"])
        self._validate_text_property(command, self._property_id(), writable=True)
        for property_id in self._mailbox_marker(command, writable=True):
            self._validate_text_property(command, property_id, writable=True)

        # The upstream handler dry-runs its invocation gate without persisting
        # anything. The create endpoint remains authoritative when sent.
        preview = _object(self._http.request(
            "POST", "/api/issues/preview-trigger", workspace_id=command.workspace_id,
            body={**payload, "is_create": True},
        ), "preview_trigger")
        triggers = _rows(preview, "triggers", "preview_trigger")
        _check_total(preview, len(triggers), "preview_trigger", field="total_count")
        if len(triggers) != 1:
            raise NativeHTTPError("preview_trigger", "coordinator_trigger_unverified")
        trigger = triggers[0]
        _match_id(trigger, "agent_id", command.coordinator_id, "preview_trigger")
        if trigger.get("source") != "assign" or trigger.get("issue_id") != "":
            raise NativeHTTPError("preview_trigger", "unexpected_trigger")

    def _check_status(self, command: DispatchCommand, project: dict, status: str) -> None:
        catalog = self._get(command, "/api/issue-statuses", "status_catalog")
        statuses = _rows(catalog, "statuses", "status_catalog")
        _check_total(catalog, len(statuses), "status_catalog")
        matching = [row for row in statuses if row.get("key") == status]
        if len(matching) != 1:
            raise NativeHTTPError("status_catalog", "status_unverified")
        _match_id(matching[0], "workspace_id", command.workspace_id, "status_catalog")
        _require_active(matching[0], "status_catalog")
        if "workflow_id" not in project:
            raise NativeHTTPError("project", "schema_drift", field="workflow_id")
        if project["workflow_id"] is None:
            return
        workflow_id = _uuid(project["workflow_id"], "project", "workflow_id")
        workflow = self._get(command, f"/api/issue-workflows/{workflow_id}", "workflow")
        _match_id(workflow, "id", workflow_id, "workflow")
        _match_id(workflow, "workspace_id", command.workspace_id, "workflow")
        steps = _rows(workflow, "steps", "workflow")
        if sum(step.get("status_key") == status for step in steps) != 1:
            raise NativeHTTPError("workflow", "status_unverified")

    def _check_private_project(self, command: DispatchCommand, agent: dict) -> None:
        if "owner_id" not in agent:
            raise NativeHTTPError("agent", "schema_drift", field="owner_id")
        if agent["owner_id"] is None:
            return
        owner_id = _uuid(agent["owner_id"], "agent", "owner_id")
        result = self._get(command, f"/api/projects/{command.project_id}/members", "project_members")
        members = _rows(result, "members", "project_members")
        _check_total(result, len(members), "project_members")
        for member in members:
            _match_id(member, "project_id", command.project_id, "project_members")
        if not any(_uuid(member.get("user_id"), "project_members", "user_id") == owner_id for member in members):
            raise NativeHTTPError("project_members", "coordinator_owner_not_member")

    def create_issue(self, command: DispatchCommand, correlation: str) -> IssueReference:
        if command.instance_id != self.instance_id:
            raise UnverifiedIssue("native adapter does not match the requested instance")
        fields = self._assignee(command)
        self._check_correlation(correlation)
        markers = {self._property_id(): correlation, **self._mailbox_marker(command, writable=True)}
        payload = {**fields, "title": command.new_issue.title, "description": command.new_issue.description,
                   "properties": markers}
        created = _object(self._http.request(
            "POST", "/api/issues", workspace_id=command.workspace_id, body=payload,
        ), "issue_create")
        result = self._verified_issue(command, created, expected_creator=True)
        self._verify_marker(created, "properties", self._property_id(), correlation)
        _match_id(created, "assignee_id", command.coordinator_id, "issue_create")
        if created.get("assignee_type") != "agent" or created.get("status") != fields["status"]:
            raise UnverifiedIssue("native Issue create response does not match the requested assignment")
        detail = self._get(command, f"/api/issues/{result.issue_id}", "issue")
        ref = self._verified_issue(command, detail, issue_id=result.issue_id, expected_creator=True)
        self._verify_marker(detail, "properties", self._property_id(), correlation)
        self._verify_mailbox_reference(command, detail)
        return ref
