"""ASGI middleware for request IDs and one structured access log per request.

The middleware never reads or logs request bodies, authorization headers, or
query strings.  It adds ``X-Request-ID`` to the response and records method,
path, status, duration, client address, owner, and job ID when known.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from starlette.datastructures import Headers, MutableHeaders

from .observability import (
    REQUEST_ID_HEADER,
    client_ip_var,
    extract_job_id,
    log_event,
    new_request_id,
    normalize_request_id,
    request_id_var,
)


def _owner_from_scope(scope: dict[str, Any]) -> str | None:
    state = scope.get("state")
    if isinstance(state, dict):
        return state.get("owner_id")
    return getattr(state, "owner_id", None)


def _resolve_client_ip(scope: dict[str, Any], headers: Headers) -> str | None:
    """Return the address of the client that opened the connection.

    The API is reached through Caddy, which resolves the real client from
    the proxy chain and rewrites X-Forwarded-For to that single value.  The
    socket peer is the local proxy in that case, so reading the header is
    what keeps the per-IP login limiter and the audit trail meaningful.
    """

    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        entries = [part.strip() for part in forwarded.split(",") if part.strip()]
        if entries:
            return entries[0][:64]
    client = scope.get("client")
    return client[0] if client else None


class RequestContextMiddleware:
    """Attach a request ID, bind context variables, and log completion."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = normalize_request_id(
            headers.get(REQUEST_ID_HEADER)
        ) or new_request_id()
        client = scope.get("client")
        settings = scope["app"].state.settings
        if settings.trust_forwarded_for:
            client_ip = _resolve_client_ip(scope, headers)
        else:
            client_ip = client[0] if client else None
        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))[:512]
        job_id = extract_job_id(path)

        request_token = request_id_var.set(request_id)
        client_token = client_ip_var.set(client_ip)
        started = time.monotonic()
        status_code: int | None = None

        async def send_with_request_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                mutable = MutableHeaders(scope=message)
                mutable[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            log_event(
                "request.failed",
                level=logging.ERROR,
                method=method,
                path=path,
                status_code=status_code or 500,
                duration_ms=round(
                    (time.monotonic() - started) * 1000, 3
                ),
                client_ip=client_ip,
                owner_id=_owner_from_scope(scope),
                job_id=job_id,
            )
            raise
        else:
            log_event(
                "request.completed",
                method=method,
                path=path,
                status_code=status_code or 500,
                duration_ms=round(
                    (time.monotonic() - started) * 1000, 3
                ),
                client_ip=client_ip,
                owner_id=_owner_from_scope(scope),
                job_id=job_id,
            )
        finally:
            request_id_var.reset(request_token)
            client_ip_var.reset(client_token)
