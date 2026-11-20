"""Read adapter for the pinned Multica REST contract."""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from ipaddress import ip_address, ip_network
import json
import re
from urllib.parse import urlsplit
from uuid import UUID


CONTRACT_BASELINE = "v0.11.0"
CONTRACT_SOURCE_COMMIT = "cb190810a659c1a61c4a86d9f6ecfc9df4b086d8"
_RESPONSE_LIMIT = 8 * 1024 * 1024
_PRIVATE_IPV4 = tuple(ip_network(block) for block in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_ROUTES = {
    "identity": "/api/me",
    "project": "/api/projects/{project_id}",
    "issue": "/api/issues/{issue_id}",
    "runs": "/api/issues/{issue_id}/task-runs?scope=issue&view=timeline",
}
_HTTP_CODES = {401: "unauthenticated", 403: "forbidden", 404: "not_found_or_hidden", 429: "rate_limited"}


class MulticaAPIError(Exception):
    """A diagnostic containing only the adapter's labels and an optional HTTP status."""

    def __init__(self, check, code, *, field=None, http_status=None):
        super().__init__(f"{check}: {code}" + (f" ({field})" if field is not None else ""))
        self.check = check
        self.code = code
        self.field = field
        self.http_status = http_status

    def diagnostic(self):
        details = {"code": self.code}
        if self.field is not None:
            details["field"] = self.field
        if self.http_status is not None:
            details["http_status"] = self.http_status
        return details


@dataclass(frozen=True)
class Project:
    id: str
    workspace_id: str


@dataclass(frozen=True)
class Issue:
    id: str
    workspace_id: str
    project_id: str
    status: str


@dataclass(frozen=True)
class Run:
    id: str
    issue_id: str
    workspace_id: str
    project_id: str  # Project of the Issue observed in this read chain.
    status: str
    completed_at: str | None


def _uuid(value, check, field):
    if isinstance(value, str):
        try:
            canonical = str(UUID(value))
            if value.lower() == canonical:
                return canonical
        except ValueError:
            pass
    code = "invalid_input" if check == "configuration" else "schema_drift"
    raise MulticaAPIError(check, code, field=field)


def _match_id(obj, field, expected, check):
    actual = _uuid(obj.get(field), check, field)
    if actual != expected:
        code = "identity_mismatch" if check == "identity" else "scope_mismatch"
        raise MulticaAPIError(check, code, field=field)


def _status(obj, check):
    status = obj.get("status")
    if not isinstance(status, str) or not status.strip():
        raise MulticaAPIError(check, "schema_drift", field="status")
    return status


def _completed_at(row):
    if "completed_at" in row:
        value = row["completed_at"]
        if value is None:
            return None
        if isinstance(value, str):
            try:
                timestamp = value[:-1] + "+00:00" if value.endswith("Z") else value
                if datetime.fromisoformat(timestamp).utcoffset() is not None:
                    return value
            except (ValueError, OverflowError):
                pass
    raise MulticaAPIError("runs", "schema_drift", field="completed_at")


def _parse_origin(origin, allow_private_http):
    try:
        if (not isinstance(origin, str) or re.fullmatch(r"[\x21-\x7e]+", origin) is None
                or "?" in origin or "#" in origin):
            raise ValueError
        parts = urlsplit(origin)
        host, port = parts.hostname, parts.port
        if not host or parts.path not in ("", "/"):
            raise ValueError
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if ":" in host and address is not None and "%" not in host:
            authority = f"[{host}]"
        elif re.fullmatch(r"[a-z0-9.-]+", host):
            authority = host
        else:
            raise ValueError
        if port is not None:
            authority += f":{port}"
        if parts.netloc.lower() != authority or port == 0:
            raise ValueError
        if parts.scheme == "https":
            return parts.scheme, host, port
        if parts.scheme == "http" and address is not None:
            if address.is_loopback or (allow_private_http and any(address in network for network in _PRIVATE_IPV4)):
                return parts.scheme, host, port
    except ValueError:
        pass
    raise MulticaAPIError("configuration", "invalid_origin", field="origin")


class MulticaAPI:
    """Bind reads to one service-supplied origin, bearer, expected user, workspace and project.

    Build this from trusted service configuration after authorizing the caller.
    Tool call inputs should provide only resource UUIDs, never connection or identity settings.
    Each resource read verifies the bearer identity and the relevant scope again.
    Enable allow_private_http only for an operator-verified encrypted overlay and
    fixed RFC 1918 IPv4 origin. Transport security on that path belongs to the overlay.
    """

    def __init__(
        self, *, origin: str, token: str, expected_user_id: str, workspace_id: str,
        project_id: str, allow_private_http: bool = False,
    ):
        self._scheme, self._host, self._port = _parse_origin(origin, allow_private_http is True)
        if not isinstance(token, str) or re.fullmatch(r"[\x21-\x7e]+", token) is None:
            raise MulticaAPIError("configuration", "invalid_credential")
        self._token = token
        self._user_id = _uuid(expected_user_id, "configuration", "expected_user_id")
        self._workspace_id = _uuid(workspace_id, "configuration", "workspace_id")
        self._project_id = _uuid(project_id, "configuration", "project_id")

    def _read(self, check, expected_type, **path_ids):
        path = _ROUTES[check].format(**path_ids)
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if check != "identity":
            headers["X-Workspace-ID"] = self._workspace_id
        # Like the reporter's HTTP transport, direct connections ignore proxy env and redirects.
        connection = HTTPSConnection if self._scheme == "https" else HTTPConnection
        try:
            with closing(connection(self._host, self._port, timeout=10)) as conn:
                conn.request("GET", path, headers=headers)
                with conn.getresponse() as response:
                    if response.status != 200:
                        if 300 <= response.status < 400:
                            raise MulticaAPIError(check, "redirect_refused", http_status=response.status)
                        code = _HTTP_CODES.get(response.status, "http_error")
                        raise MulticaAPIError(check, code, http_status=response.status)
                    raw = response.read(_RESPONSE_LIMIT + 1)
        except TimeoutError:
            raise MulticaAPIError(check, "timeout") from None
        except (OSError, HTTPException):
            raise MulticaAPIError(check, "transport_error") from None
        if len(raw) > _RESPONSE_LIMIT:
            raise MulticaAPIError(check, "response_too_large")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            raise MulticaAPIError(check, "invalid_json") from None
        if not isinstance(result, expected_type):
            raise MulticaAPIError(check, "schema_drift")
        return result

    def verify_identity(self) -> str:
        user = self._read("identity", dict)
        _match_id(user, "id", self._user_id, "identity")
        return self._user_id

    def get_project(self) -> Project:
        self.verify_identity()
        project = self._read("project", dict, project_id=self._project_id)
        _match_id(project, "id", self._project_id, "project")
        _match_id(project, "workspace_id", self._workspace_id, "project")
        return Project(self._project_id, self._workspace_id)

    def get_issue(self, issue_id: str) -> Issue:
        issue_id = _uuid(issue_id, "configuration", "issue_id")
        project = self.get_project()
        issue = self._read("issue", dict, issue_id=issue_id)
        _match_id(issue, "id", issue_id, "issue")
        _match_id(issue, "workspace_id", project.workspace_id, "issue")
        if "project_id" in issue and issue["project_id"] is None:
            raise MulticaAPIError("issue", "scope_mismatch", field="project_id")
        _match_id(issue, "project_id", project.id, "issue")
        return Issue(issue_id, project.workspace_id, project.id, _status(issue, "issue"))

    def list_issue_runs(self, issue_id: str) -> list[Run]:
        """Read bounded-by-size visible timeline history for this Issue at v0.11.0."""
        issue = self.get_issue(issue_id)
        rows = self._read("runs", list, issue_id=issue.id)
        runs = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise MulticaAPIError("runs", "schema_drift")
            run_id = _uuid(row.get("id"), "runs", "id")
            _match_id(row, "issue_id", issue.id, "runs")
            _match_id(row, "workspace_id", issue.workspace_id, "runs")
            # v0.11.0 omits project_id in timeline rows; if emitted, it must agree.
            if "project_id" in row:
                _match_id(row, "project_id", issue.project_id, "runs")
            restricted = row.get("restricted", False)
            if not isinstance(restricted, bool):
                raise MulticaAPIError("runs", "schema_drift", field="restricted")
            if restricted:
                raise MulticaAPIError("runs", "restricted_run", field="restricted")
            if run_id in seen:
                raise MulticaAPIError("runs", "duplicate_run", field="id")
            seen.add(run_id)
            runs.append(Run(run_id, issue.id, issue.workspace_id, issue.project_id,
                            _status(row, "runs"), _completed_at(row)))
        return runs

    def get_run(self, issue_id: str, run_id: str) -> Run:
        run_id = _uuid(run_id, "configuration", "run_id")
        for run in self.list_issue_runs(issue_id):
            if run.id == run_id:
                return run
        raise MulticaAPIError("exact_run", "run_not_found")

    def check_contract(self, issue_id: str, run_id: str) -> dict:
        """Use the same reads as the service, returning labels instead of resource data."""
        error = None
        try:
            self.get_run(issue_id, run_id)
        except MulticaAPIError as exc:
            error = exc

        checks = []
        blocked = error is not None and error.check == "configuration"
        if blocked:
            checks.append({"check": "configuration", "status": "fail", **error.diagnostic()})
        for name in (*_ROUTES, "exact_run"):
            row = {"check": name, "status": "not_run" if blocked else "pass"}
            if name in _ROUTES:
                row["route"] = _ROUTES[name]
            if error is not None and error.check == name:
                row.update(status="fail", **error.diagnostic())
                blocked = True
            checks.append(row)
        status = "pass"
        if error is not None:
            status = "not_run" if error.check == "configuration" else "fail"
        report = {"schema_version": 1, "contract_baseline": CONTRACT_BASELINE,
                  "contract_source_commit": CONTRACT_SOURCE_COMMIT, "status": status, "checks": checks}
        if status != "not_run":
            report["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return report
