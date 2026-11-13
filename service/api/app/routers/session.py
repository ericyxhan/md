"""Browser session endpoints.

These routes live outside the authenticated ``/api/v1`` dependency so that a
browser can sign in before it owns a session.  The login endpoint has its own
per-IP token bucket; all other public routes keep the normal per-owner limiter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..observability import current_client_ip, log_event
from ..schemas import SessionLogin, SessionOut, UserOut
from ..session import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    Session,
    issue_session,
    session_from_request,
    sessions_configured,
    verify_csrf,
)
from ..users import authenticate, get_user, record_login, user_to_dict

router = APIRouter(prefix="/api/v1/session", tags=["session"])


def _admin_email(request: Request, session: Session) -> str:
    """Return the email address of the administrator account."""

    admin_id = getattr(request.app.state, "admin_owner_id", None)
    if admin_id is None:
        return ""
    account = get_user(session, admin_id)
    return account.email if account is not None else ""


@router.get("", response_model=SessionOut)
def describe_session(request: Request) -> SessionOut:
    """Return the current browser session without requiring one."""

    settings = request.app.state.settings
    if not sessions_configured(settings):
        return SessionOut(authenticated=False)
    session = session_from_request(request)
    if session is None:
        return SessionOut(authenticated=False)

    account = None
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is not None:
        with session_factory() as db:
            found = get_user(db, session.subject)
            if found is not None and found.is_active:
                account = found

    if account is None:
        # The account was removed or deactivated after the cookie was
        # issued; the session no longer grants access.
        return SessionOut(authenticated=False)

    return SessionOut(
        authenticated=True,
        owner=session.subject,
        issued_at=session.to_dict()["issued_at"],
        expires_at=session.to_dict()["expires_at"],
        auth_method="cookie",
        user=UserOut(**user_to_dict(account)),
    )


@router.post("", response_model=SessionOut)
def login(
    request: Request,
    body: SessionLogin,
    response: Response,
    session: Session = Depends(get_session),
) -> SessionOut:
    settings = request.app.state.settings
    if not sessions_configured(settings):
        raise APIError(
            503,
            "session_not_configured",
            "Browser sign-in is not enabled on this server",
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

    email = (body.email or "").strip()
    if not email:
        # No address given: fall back to the administrator account so the
        # shared-lab sign-in of the pre-accounts deployment keeps working.
        email = _admin_email(request, session)
        if not email:
            raise APIError(
                401,
                "invalid_credentials",
                "Incorrect email address or password",
            )

    account = authenticate(session, email, body.password)
    if account is None:
        log_event(
            "audit.session.denied",
            action="session.login",
            outcome="denied",
            client_ip=current_client_ip(),
        )
        raise APIError(
            401,
            "invalid_credentials",
            "Incorrect email address or password",
        )

    record_login(session, account)
    session.commit()

    session_state = issue_session(request, response, account.id)

    log_event(
        "session.login",
        action="session.login",
        outcome="success",
        owner_id=account.id,
        client_ip=current_client_ip(),
    )
    return SessionOut(
        authenticated=True,
        owner=account.id,
        issued_at=session_state.to_dict()["issued_at"],
        expires_at=session_state.to_dict()["expires_at"],
        auth_method="cookie",
        user=UserOut(**user_to_dict(account)),
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
