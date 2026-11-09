"""Bearer-token authentication and public rate limiting."""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, Header, Request

from .errors import APIError
from .observability import current_client_ip, log_event
from .session import session_from_request, sessions_configured, verify_csrf

OWNER_ID = "local"


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _audit_denied(request: Request, action: str, reason: str) -> None:
    log_event(
        f"audit.{action}",
        level=logging.WARNING,
        action=action,
        outcome="denied",
        reason=reason,
        path=request.url.path[:512],
        method=request.method,
        client_ip=current_client_ip(),
    )


def require_owner(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    """Authenticate a public API caller and return the owner ID.

    Accepts either the machine bearer token or a signed browser session
    cookie.  Cookie-authenticated mutating requests must also echo the CSRF
    token, which is checked before any handler runs.
    """

    settings = request.app.state.settings
    token = _bearer_token(authorization)

    if token is not None:
        if not settings.service_api_token:
            raise APIError(
                503,
                "auth_not_configured",
                "SERVICE_API_TOKEN is not configured",
            )
        if not secrets.compare_digest(token, settings.service_api_token):
            _audit_denied(request, "auth.denied", "invalid_public_token")
            raise APIError(
                401,
                "unauthorized",
                "Missing or invalid bearer token",
            )
        request.state.owner_id = OWNER_ID
        request.state.auth_method = "bearer"
        return OWNER_ID

    session = session_from_request(request)
    if session is not None:
        verify_csrf(request)
        request.state.owner_id = session.subject
        request.state.auth_method = "session"
        return session.subject

    if not settings.service_api_token and not sessions_configured(settings):
        raise APIError(
            503,
            "auth_not_configured",
            "No public authentication method is configured",
        )

    _audit_denied(request, "auth.denied", "missing_credentials")
    raise APIError(
        401,
        "unauthorized",
        "Sign in to continue",
    )


def require_worker(
    request: Request,
    x_worker_token: str | None = Header(default=None),
) -> None:
    """Authenticate an internal worker request."""

    settings = request.app.state.settings
    if not settings.worker_token:
        raise APIError(
            503,
            "worker_auth_not_configured",
            "WORKER_TOKEN is not configured",
        )
    if x_worker_token is None or not secrets.compare_digest(
        x_worker_token, settings.worker_token
    ):
        _audit_denied(request, "worker_auth.denied", "invalid_worker_token")
        raise APIError(401, "unauthorized", "Missing or invalid worker token")


def rate_limit(
    request: Request,
    owner: str = Depends(require_owner),
) -> None:
    """Charge one token for an authenticated public request."""

    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    retry_after = limiter.consume(owner)
    if retry_after is None:
        return

    log_event(
        "audit.rate_limit.denied",
        level=logging.WARNING,
        action="rate_limit.denied",
        outcome="denied",
        owner_id=owner,
        retry_after_seconds=retry_after,
        path=request.url.path[:512],
        method=request.method,
        client_ip=current_client_ip(),
    )
    raise APIError(
        429,
        "rate_limit_exceeded",
        "Too many requests for this owner",
        {
            "retry_after_seconds": retry_after,
            "limit_per_minute": int(limiter.capacity),
        },
        headers={"Retry-After": str(retry_after)},
    )
