"""Minimal Microsoft Graph HTTP helpers."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .session_logging import get_active_session


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class GraphApiError(RuntimeError):
    """Raised when Microsoft Graph returns a non-success response."""


def _build_url(path: str, query: dict[str, str] | None = None) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = f"{GRAPH_BASE_URL}{normalized_path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    return url


def _sanitize_path(path: str) -> str:
    segments = []
    for segment in path.strip("/").split("/"):
        if not segment:
            continue
        if "@" in segment:
            segments.append("<email>")
        elif GUID_RE.fullmatch(segment):
            segments.append("<id>")
        elif len(segment) >= 16 and any(char.isdigit() for char in segment):
            segments.append("<id>")
        else:
            segments.append(segment)
    return "/" + "/".join(segments)


def _summarize_payload(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, dict):
        summary: dict[str, Any] = {
            "type": "object",
            "keys": sorted(value.keys()),
        }
        if depth < 2:
            summary["fields"] = {
                key: _summarize_payload(item, depth=depth + 1) for key, item in value.items()
            }
        return summary
    if isinstance(value, list):
        summary = {"type": "array", "length": len(value)}
        if depth < 2 and value:
            summary["items"] = [_summarize_payload(value[0], depth=depth + 1)]
        return summary
    if isinstance(value, str):
        return {"type": "string", "length": len(value)}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def _summarize_error_body(response_body: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "body_type": "text",
        "body_length": len(response_body),
    }
    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError:
        return summary

    summary["body_type"] = "json"
    summary["body_shape"] = _summarize_payload(parsed)
    if isinstance(parsed, dict):
        error_object = parsed.get("error")
        if isinstance(error_object, dict) and isinstance(error_object.get("code"), str):
            summary["error_code"] = error_object["code"]
    return summary


def _format_http_error(path: str, status_code: int, response_body: str) -> GraphApiError:
    normalized_path = path if path.startswith("/") else f"/{path}"
    sanitized_path = _sanitize_path(normalized_path)
    return GraphApiError(
        f"Graph request {sanitized_path} failed with HTTP {status_code}: {response_body}"
    )


def graph_get_json(
    *,
    access_token: str,
    path: str,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = _build_url(path, query)
    request_id = uuid.uuid4().hex
    session = get_active_session()
    started_at = time.perf_counter()

    if session:
        request_event: dict[str, Any] = {
            "request_id": request_id,
            "operation_type": "read",
            "method": "GET",
            "path": _sanitize_path(normalized_path),
            "query_keys": sorted((query or {}).keys()),
        }
        if session.debug_enabled:
            request_event["url"] = url
            request_event["query"] = query or {}
        session.log_event("graph_request", **request_event)

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
            parsed_payload = json.loads(payload)
            if session:
                response_event: dict[str, Any] = {
                    "request_id": request_id,
                    "operation_type": "read",
                    "method": "GET",
                    "path": _sanitize_path(normalized_path),
                    "status": response.status,
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_shape": _summarize_payload(parsed_payload),
                }
                if session.debug_enabled:
                    response_event["response_json"] = parsed_payload
                session.log_event("graph_response", **response_event)
            return parsed_payload
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        if session:
            error_event: dict[str, Any] = {
                "request_id": request_id,
                "operation_type": "read",
                "method": "GET",
                "path": _sanitize_path(normalized_path),
                "status": exc.code,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "error_summary": _summarize_error_body(response_body),
            }
            if session.debug_enabled:
                error_event["error_body"] = response_body
            session.log_event("graph_error", **error_event)
        raise _format_http_error(normalized_path, exc.code, response_body) from exc
    except URLError as exc:
        if session:
            session.log_event(
                "graph_error",
                request_id=request_id,
                operation_type="read",
                method="GET",
                path=_sanitize_path(normalized_path),
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error_reason=str(exc.reason),
            )
        raise GraphApiError(
            f"Graph GET {_sanitize_path(normalized_path)} failed: {exc.reason}"
        ) from exc


def graph_post_json(
    *,
    access_token: str,
    path: str,
    json_body: dict[str, Any],
    query: dict[str, str] | None = None,
    expected_statuses: tuple[int, ...] = (200, 201, 202, 204),
) -> dict[str, Any] | None:
    normalized_path = path if path.startswith("/") else f"/{path}"
    url = _build_url(path, query)
    request_id = uuid.uuid4().hex
    session = get_active_session()
    started_at = time.perf_counter()

    if session:
        request_event = {
            "request_id": request_id,
            "operation_type": "write",
            "method": "POST",
            "path": _sanitize_path(normalized_path),
            "query_keys": sorted((query or {}).keys()),
            "request_shape": _summarize_payload(json_body),
        }
        if session.debug_enabled:
            request_event["url"] = url
            request_event["query"] = query or {}
            request_event["request_json"] = json_body
        session.log_event("graph_request", **request_event)

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=json.dumps(json_body).encode("utf-8"),
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            if response.status not in expected_statuses:
                if session:
                    session.log_event(
                        "graph_error",
                        request_id=request_id,
                        operation_type="write",
                        method="POST",
                        path=_sanitize_path(normalized_path),
                        status=response.status,
                        elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                        error_summary={"reason": "unexpected_success_status"},
                    )
                raise GraphApiError(
                    f"Graph POST {normalized_path} returned unexpected HTTP {response.status}."
                )
            payload = response.read().decode("utf-8")
            parsed_payload = json.loads(payload) if payload.strip() else None
            if session:
                response_event = {
                    "request_id": request_id,
                    "operation_type": "write",
                    "method": "POST",
                    "path": _sanitize_path(normalized_path),
                    "status": response.status,
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    "response_shape": _summarize_payload(parsed_payload),
                }
                if session.debug_enabled:
                    response_event["response_json"] = parsed_payload
                session.log_event("graph_response", **response_event)
            return parsed_payload
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        if session:
            error_event = {
                "request_id": request_id,
                "operation_type": "write",
                "method": "POST",
                "path": _sanitize_path(normalized_path),
                "status": exc.code,
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 2),
                "error_summary": _summarize_error_body(response_body),
            }
            if session.debug_enabled:
                error_event["error_body"] = response_body
            session.log_event("graph_error", **error_event)
        raise _format_http_error(normalized_path, exc.code, response_body) from exc
    except URLError as exc:
        if session:
            session.log_event(
                "graph_error",
                request_id=request_id,
                operation_type="write",
                method="POST",
                path=_sanitize_path(normalized_path),
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error_reason=str(exc.reason),
            )
        raise GraphApiError(
            f"Graph POST {_sanitize_path(normalized_path)} failed: {exc.reason}"
        ) from exc
