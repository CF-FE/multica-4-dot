"""Single-attempt JSON transport to a configured Multica origin."""

from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection, HTTPException, HTTPSConnection
import json
import re
from typing import Any

from .multica_api import MulticaAPIError, _HTTP_CODES, _RESPONSE_LIMIT, _parse_origin, _uuid


NativeHTTPError = MulticaAPIError
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_ERROR_CODES = {**_HTTP_CODES, 400: "bad_request", 409: "conflict", 422: "unprocessable"}


class NativeHTTP:
    """Use a service-owned origin and credential. Paths are built by native adapters."""

    def __init__(
        self, *, origin: str, token: str, allow_private_http: bool = False, timeout: float = 10,
    ) -> None:
        self._scheme, self._host, self._port = _parse_origin(origin, allow_private_http is True)
        if not isinstance(token, str) or re.fullmatch(r"[\x21-\x7e]+", token) is None:
            raise NativeHTTPError("configuration", "invalid_credential")
        if type(timeout) not in (int, float) or not 0 < timeout < float("inf"):
            raise NativeHTTPError("configuration", "invalid_input", field="timeout")
        self._token = token
        self._timeout = timeout

    def request(
        self, method: str, path: str, *, workspace_id: str | None = None, body: Any = None,
    ) -> Any:
        """Return parsed JSON or None for an empty 2xx. Never retry or follow redirects."""
        if (
            method not in _METHODS
            or not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or "#" in path
            or re.fullmatch(r"[\x21-\x7e]+", path) is None
        ):
            raise NativeHTTPError("request", "invalid_input")
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if workspace_id is not None:
            headers["X-Workspace-ID"] = _uuid(workspace_id, "configuration", "workspace_id")
        payload = None
        if body is not None:
            try:
                payload = json.dumps(body, allow_nan=False).encode("utf-8")
            except (TypeError, ValueError, RecursionError):
                raise NativeHTTPError("request", "invalid_json_body") from None
            headers["Content-Type"] = "application/json"

        connection = HTTPSConnection if self._scheme == "https" else HTTPConnection
        try:
            with closing(connection(self._host, self._port, timeout=self._timeout)) as conn:
                conn.request(method, path, body=payload, headers=headers)
                with conn.getresponse() as response:
                    if not 200 <= response.status < 300:
                        code = (
                            "redirect_refused" if 300 <= response.status < 400
                            else _ERROR_CODES.get(response.status, "http_error")
                        )
                        raise NativeHTTPError("request", code, http_status=response.status)
                    raw = response.read(_RESPONSE_LIMIT + 1)
                    if len(raw) > _RESPONSE_LIMIT:
                        raise NativeHTTPError("request", "response_too_large")
                    if response.length:
                        raise NativeHTTPError("request", "incomplete_response")
        except TimeoutError:
            raise NativeHTTPError("request", "timeout") from None
        except (OSError, HTTPException):
            raise NativeHTTPError("request", "transport_error") from None
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            raise NativeHTTPError("request", "invalid_json") from None
