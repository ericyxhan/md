"""Browser session endpoints.

These routes live outside the authenticated ``/api/v1`` dependency so that a
browser can log in before it owns a session.  The login endpoint has its own
per-IP token bucket; all other public routes keep the normal per-owner limiter.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response

from ..errors import APIError
from ..observability import current_client_ip, log_event
from ..schemas import SessionLogin, SessionOut
from ..session import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    encode_session,
    session_from_request,
    session_secret,
    sessions_configured,
    verify_csrf,
    verify_password,
)

router = APIRouter(prefix="/api/v1/session", tags=["session"])

DEFAULT_OWNER = "local"


def _cookie_options(request: Request) -> dict:
    return {
        "path": "/",
        "secure": request.app.state.settings.web_cookie_secure,
        "samesite": "lax",
    }


@router.get("", response_model=SessionOut)
def describe_session(request: Request) -> SessionOut:
    """Return the current browser session without requiring one."""

    settings = request.app.state.settings
    if not sessions_configured(settings):
        return SessionOut(authenticated=False)
    session = session_from_request(request)
    if session is None:
        return SessionOut(authenticated=False)
    return SessionOut(
        authenticated=True,
        owner=session.subject,
        issued_at=session.to_dict()["issued_at"],
        expires_at=session.to_dict()["expires_at"],
        auth_method="cookie",
    )


@router.post("", response_model=SessionOut)
def login(
    request: Request,
    body: SessionLogin,
    response: Response,
) -> SessionOut:
    settings = request.app.state.settings
    if not sessions_configured(settings):
        raise APIError(
            503,
            "session_not_configured",
            "Browser sessions are not configured on this server",
        )

    limiter = getattr(request.app.state, "login_limiter", None)
    if limiter is not None:
        retry_after = limiter.consume(current_client_ip() or "unknown")
        if retry_after is not None:
            raise APIError(
                429,
                "too_many_login_attempts",
                "Too many login attempts; try again shortly",
                {"retry_after_seconds": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

    if not verify_password(settings, body.password):
        log_event(
            "audit.session.denied",
            action="session.login",
            outcome="denied",
            client_ip=current_client_ip(),
        )
        raise APIError(401, "invalid_credentials", "Incorrect lab password")

    token, session = encode_session(
        session_secret(settings),
        DEFAULT_OWNER,
        ttl_seconds=settings.web_session_ttl_seconds,
    )
    csrf_token = secrets.token_urlsafe(32)
    options = _cookie_options(request)

    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        max_age=settings.web_session_ttl_seconds,
        **options,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        max_age=settings.web_session_ttl_seconds,
        **options,
    )

    log_event(
        "session.login",
        action="session.login",
        outcome="success",
        owner_id=session.subject,
        client_ip=current_client_ip(),
    )
    return SessionOut(
        authenticated=True,
        owner=session.subject,
        issued_at=session.to_dict()["issued_at"],
        expires_at=session.to_dict()["expires_at"],
        auth_method="cookie",
    )


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    """Clear the browser session.  Safe to call with no active session."""

    if session_from_request(request) is not None:
        verify_csrf(request)

    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response
