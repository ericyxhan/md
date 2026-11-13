"""Bearer-token and session authentication, plus public rate limiting.

Two callers are authenticated here:

* machine clients, which send the static ``SERVICE_API_TOKEN`` bearer
  token and act as the administrator account;
* browsers, which send a signed session cookie whose subject is the
  account id.

Both resolve to an account id, which is the ``owner_id`` of everything the
caller may see.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, Header, Request

from .errors import APIError
from .observability import current_client_ip, log_event
from .session import session_from_request, sessions_configured, verify_csrf
from .users import find_admin, get_user


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


def admin_owner_id(request: Request) -> str | None:
    """Return the id of the administrator account, if there is one.

    The id is cached on the application state after the first lookup.  The
    lifespan normally sets it during startup; the fallback covers the case
    where the application is used without running the lifespan.
    """

    state = request.app.state
    owner = getattr(state, "admin_owner_id", None)
    if owner:
        return owner

    session_factory = getattr(state, "session_factory", None)
    if session_factory is None:  # pragma: no cover - defensive
        return None
    with session_factory() as session:
        admin = find_admin(session)
        if admin is None:
            return None
        state.admin_owner_id = admin.id
        return admin.id


def require_owner(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    """Authenticate a public API caller and return the account id.

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
        owner = admin_owner_id(request)
        if owner is None:
            raise APIError(
                503,
                "auth_not_configured",
                "No administrator account exists on this server",
            )
        request.state.owner_id = owner
        request.state.auth_method = "bearer"
        return owner

    session = session_from_request(request)
    if session is not None:
        verify_csrf(request)
        owner = _active_user_id(request, session.subject)
        if owner is None:
            _audit_denied(request, "auth.denied", "inactive_account")
            raise APIError(
                401,
                "unauthorized",
                "This account can no longer sign in",
            )
        request.state.owner_id = owner
        request.state.auth_method = "session"
        return owner

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


def _active_user_id(request: Request, user_id: str) -> str | None:
    """Return the account id when the account exists and is usable.

    The lookup happens on every request so that deactivating an account
    takes effect immediately instead of at the next sign-in.
    """

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:  # pragma: no cover - defensive
        return None
    with session_factory() as session:
        user = get_user(session, user_id)
        if user is None or not user.is_active:
            return None
        return user.id


def require_admin(
    request: Request,
    owner: str = Depends(require_owner),
) -> str:
    """Require an administrator account."""

    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:  # pragma: no cover - defensive
        raise APIError(500, "internal_error", "Session factory is unavailable")
    with session_factory() as session:
        user = get_user(session, owner)
        if user is None or not user.is_admin:
            _audit_denied(request, "auth.denied", "not_an_administrator")
            raise APIError(
                403,
                "forbidden",
                "This action requires an administrator account",
            )
    return owner


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
