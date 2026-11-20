"""Read original Task Mailbox jobs and result receipts through its existing MCP.

Configure MULTICA_BACKEND_MAILBOX_URL (full HTTPS /mcp endpoint),
MULTICA_BACKEND_MAILBOX_ACCESS_TOKEN (separate service-held Mailbox OAuth access
token), and MULTICA_BACKEND_MAILBOX_SUBJECT (exact Mailbox whoami subject).
Provision and rotate the token through the existing Mailbox OAuth flow with its
authorized account. These values come from private service configuration.

The caller must authorize the workspace/project and resolve its Mailbox
recipient before verification. Receipt reads must be scoped to a job already
linked to a caller-authorized Issue. The original Mailbox recipient is a filter.
"""

from contextlib import closing
from dataclasses import dataclass, field
import hashlib
from http.client import HTTPException, HTTPSConnection
import json
import os
import re
from urllib.parse import urlsplit


_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_UINT_MAX = 2**63 - 1
_REPORT_ROUTE = "task-mailbox:original-job"
_REPORTED = {"REPORTED_COMPLETED", "REPORTED_FAILED", "UNKNOWN"}
_PROTOCOLS = {"2025-11-25", "2025-06-18", "2025-03-26"}
_BODY_LIMIT = 8 * 1024 * 1024
_ACK_PAGE_SIZE = 100
_ACK_PAGE_LIMIT = 12
_TOOL_ERRORS = {
    "AUTHORIZATION_DENIED": "forbidden",
    "NOT_FOUND": "not_found",
    "STORAGE_UNAVAILABLE": "unavailable",
    "STORAGE_FULL": "unavailable",
}


class MailboxError(Exception):
    """Stable failure labels without remote response bodies or credentials."""

    def __init__(self, code, *, http_status=None):
        super().__init__(f"task-mailbox: {code}")
        self.code = code
        self.http_status = http_status

    def diagnostic(self):
        info = {"code": self.code}
        if self.http_status is not None:
            info["http_status"] = self.http_status
        return info


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _text(value):
    return isinstance(value, str) and bool(value) and value == value.strip() and value.isprintable()


def _uint(value, minimum=0):
    return type(value) is int and minimum <= value <= _UINT_MAX


def _canonical_digest(data):
    try:
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise MailboxError("protocol_error") from None
    return hashlib.sha256(raw).hexdigest()


class _ReadSession:
    """Client for the pinned Mailbox deployment's stateless JSON transport.

    https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
    https://github.com/CF-FE/task-mailbox-mcp/blob/55217ff344021c34d227ac26fe38de61826bc3e3/server.py#L312
    """

    def __init__(self, endpoint, token):
        self.endpoint = endpoint
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"}
        self.request_id = 0

    def post(self, method, params=None, *, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            self.request_id += 1
            message["id"] = self.request_id
        try:
            with closing(HTTPSConnection(self.endpoint.hostname, self.endpoint.port, timeout=10)) as conn:
                conn.request("POST", self.endpoint.path, body=json.dumps(message).encode(), headers=self.headers)
                with conn.getresponse() as response:
                    expected = 202 if notification else 200
                    if response.status != expected:
                        code = {401: "unauthenticated", 403: "forbidden", 429: "rate_limited"}.get(
                            response.status, "unavailable" if response.status >= 500 else "protocol_error",
                        )
                        if 300 <= response.status < 400:
                            code = "redirect_refused"
                        raise MailboxError(code, http_status=response.status)
                    if notification:
                        return None
                    if (response.getheader("Mcp-Session-Id") is not None
                            or response.headers.get_content_type() != "application/json"):
                        raise MailboxError("unsupported_transport")
                    raw = response.read(_BODY_LIMIT + 1)
        except (OSError, HTTPException):
            raise MailboxError("unavailable") from None
        if len(raw) > _BODY_LIMIT:
            raise MailboxError("response_too_large")
        try:
            envelope = json.loads(raw)
        except (ValueError, RecursionError):
            raise MailboxError("protocol_error") from None
        if (not isinstance(envelope, dict) or envelope.get("jsonrpc") != "2.0"
                or type(envelope.get("id")) is not int or envelope["id"] != message["id"]
                or "error" in envelope or not isinstance(envelope.get("result"), dict)):
            raise MailboxError("protocol_error")
        return envelope["result"]

    def tool(self, name, **arguments):
        outcome = self.post("tools/call", {"name": name, "arguments": arguments})
        content = outcome.get("content")
        message = None
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
            if content[0].get("type") == "text" and isinstance(content[0].get("text"), str):
                message = content[0]["text"]
        if outcome.get("isError") is True:
            if message is not None:
                code = message.removeprefix(f"Error calling tool '{name}': ").partition(":")[0]
                raise MailboxError(_TOOL_ERRORS.get(code, "tool_error"))
            raise MailboxError("tool_error")
        if outcome.get("isError", False) is not False:
            raise MailboxError("protocol_error")
        data = outcome.get("structuredContent")
        if data is None and message is not None:
            try:
                data = json.loads(message)
            except (ValueError, RecursionError):
                raise MailboxError("protocol_error") from None
        if not isinstance(data, dict):
            raise MailboxError("protocol_error")
        return data


@dataclass(frozen=True)
class Mailbox:
    endpoint: str
    access_token: str = field(repr=False)
    expected_subject: str

    @classmethod
    def from_env(cls) -> "Mailbox":
        """Read private configuration without validating it or opening a connection."""
        return cls(os.getenv("MULTICA_BACKEND_MAILBOX_URL", ""),
                   os.getenv("MULTICA_BACKEND_MAILBOX_ACCESS_TOKEN", ""),
                   os.getenv("MULTICA_BACKEND_MAILBOX_SUBJECT", ""))

    def _session(self):
        if not (self.endpoint and self.access_token and self.expected_subject):
            raise MailboxError("not_configured")
        try:
            endpoint = urlsplit(self.endpoint)
            if (not re.fullmatch(r"[\x21-\x7e]+", self.endpoint) or endpoint.scheme != "https"
                    or not endpoint.hostname or endpoint.username is not None or endpoint.password is not None
                    or "?" in self.endpoint or "#" in self.endpoint or not endpoint.path.endswith("/mcp")
                    or "\\" in self.endpoint or endpoint.port == 0):
                raise ValueError
        except ValueError:
            raise MailboxError("invalid_endpoint") from None
        if not re.fullmatch(r"[\x21-\x7e]+", self.access_token) or not _text(self.expected_subject):
            raise MailboxError("invalid_credential")

        session = _ReadSession(endpoint, self.access_token)
        hello = session.post("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "multica-backend", "version": "1.0.0"},
        })
        version, capabilities = hello.get("protocolVersion"), hello.get("capabilities")
        if (not isinstance(version, str) or version not in _PROTOCOLS
                or not isinstance(capabilities, dict) or not isinstance(capabilities.get("tools"), dict)):
            raise MailboxError("unsupported_protocol")
        session.headers["MCP-Protocol-Version"] = version
        session.post("notifications/initialized", notification=True)
        identity = session.tool("whoami")
        if (identity.get("subject") != self.expected_subject or identity.get("service") != "task-mailbox"
                or identity.get("execution_enabled") is not False):
            raise MailboxError("identity_mismatch")
        return session

    @staticmethod
    def _read_job(session, job_id):
        job = session.tool("get_job", job_id=job_id)
        payload, payload_hash = job.get("payload"), job.get("payload_hash")
        status, latest = job.get("status"), job.get("latest_result_version")
        if (job.get("job_id") != job_id or not isinstance(payload, dict)
                or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1
                or not _text(payload.get("recipient")) or not _matches(_SHA256, payload_hash)
                or type(job.get("cancel_requested")) is not bool or not _uint(latest)
                or not isinstance(status, str) or (status != "PERSISTED" and status not in _REPORTED)
                or (status == "PERSISTED") != (latest == 0)):
            raise MailboxError("protocol_error")
        if payload_hash != _canonical_digest(payload):
            raise MailboxError("payload_hash_mismatch")
        return job

    def verify_job(self, *, job_id, payload_hash, instance_id, workspace_id, project_id, coordinator_id, recipient) -> dict:
        """Verify the frozen job reference before an already authorized native dispatch."""
        if (not _matches(_ID, job_id) or not _matches(_SHA256, payload_hash)
                or not all(_text(value) for value in (instance_id, workspace_id, project_id, coordinator_id, recipient))):
            raise MailboxError("invalid_input")
        job = self._read_job(self._session(), job_id)
        payload = job["payload"]
        if job["payload_hash"] != payload_hash:
            raise MailboxError("payload_hash_mismatch")
        target = payload.get("target")
        if (not isinstance(target, dict) or target.get("workspace_id") != workspace_id
                or target.get("project_id") != project_id
                or ("instance_id" in target and target["instance_id"] != instance_id)
                or ("agent_id" in target and target["agent_id"] != coordinator_id)):
            raise MailboxError("target_mismatch")
        if payload["recipient"] != recipient:
            raise MailboxError("recipient_mismatch")
        if payload.get("report_route") != _REPORT_ROUTE:
            raise MailboxError("route_mismatch")
        if job["cancel_requested"]:
            raise MailboxError("cancel_requested")
        return {"job_id": job_id, "payload_hash": payload_hash, "report_route": _REPORT_ROUTE,
                "status": job["status"], "latest_result_version": job["latest_result_version"]}

    def receipt(self, *, job_id, version) -> dict:
        """Return the exact result and any matching observed read event."""
        if not _matches(_ID, job_id) or not _uint(version, 1):
            raise MailboxError("invalid_input")
        session = self._session()
        job = self._read_job(session, job_id)
        result = session.tool("get_result", job_id=job_id, version=version)
        checksum, status = result.get("result_hash"), result.get("status")
        if (result.get("job_id") != job_id or not _uint(result.get("version"), 1)
                or result["version"] != version or not _matches(_SHA256, checksum)
                or not isinstance(result.get("result"), dict) or not isinstance(status, str)
                or status not in _REPORTED or not _matches(_ID, result.get("event_id"))
                or not _text(result.get("created_at"))):
            raise MailboxError("protocol_error")
        if _canonical_digest(result["result"]) != checksum:
            raise MailboxError("result_hash_mismatch")

        read_state, read_ack = self._find_ack(session, job_id, version, checksum, job["payload"]["recipient"])
        fields = ("job_id", "version", "result", "result_hash", "status", "event_id", "created_at")
        return {**{key: result[key] for key in fields}, "read_ack_status": read_state, "read_ack": read_ack}

    @staticmethod
    def _find_ack(session, job_id, version, checksum, recipient):
        cursor = 0
        for _ in range(_ACK_PAGE_LIMIT):
            page = session.tool("list_events", cursor=cursor, limit=_ACK_PAGE_SIZE, recipient=recipient)
            events, has_more = page.get("events"), page.get("has_more")
            if (not isinstance(events, list) or len(events) > _ACK_PAGE_SIZE or type(has_more) is not bool
                    or (has_more and not events) or not _uint(page.get("next_cursor"))):
                raise MailboxError("protocol_error")
            for event in events:
                if not isinstance(event, dict) or not _uint(event.get("cursor"), cursor + 1):
                    raise MailboxError("protocol_error")
                cursor = event["cursor"]
                if event.get("job_id") != job_id or event.get("event_type") != "RESULT_READ_ACKNOWLEDGED":
                    continue
                data = event.get("data")
                if (not isinstance(data, dict) or not _uint(data.get("version"), 1)
                        or not _matches(_SHA256, data.get("result_hash"))
                        or not _matches(_ID, event.get("event_id")) or not _text(event.get("created_at"))):
                    raise MailboxError("protocol_error")
                if data["version"] == version and data["result_hash"] == checksum:
                    return "recorded", {"event_id": event["event_id"], "cursor": cursor,
                                        "created_at": event["created_at"],
                                        "version": version, "result_hash": checksum}
            if page["next_cursor"] != cursor:
                raise MailboxError("protocol_error")
            if not has_more:
                return "not_observed", None
        return "unknown", None
