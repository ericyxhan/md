"""Account creation and administration.

Registration is public — that is the point of a public service — but it is
rate limited per client address and can be switched off entirely.  The
administrator routes manage the accounts themselves.

This router is mounted outside the authenticated ``/api/v1`` group because
registration must work before the caller has a session; every route that
needs a session carries its own dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..observability import current_client_ip, log_event
from ..passwords import verify_password_hash
from ..schemas import (
    UserAdminOut,
    UserAdminUpdate,
    UserOut,
    UserProfileUpdate,
    UserRegister,
)
from ..security import rate_limit, require_admin, require_owner
from ..services.audit import add_audit
from ..session import issue_session
from ..timeutils import utcnow_iso
from ..users import (
    create_user,
    find_by_email,
    get_user,
    list_users,
    set_password,
    user_to_dict,
    user_usage,
    validate_email,
    validate_name,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _client_limiter(request: Request):
    """Return the per-address limiter used for sign-up attempts."""

    return getattr(request.app.state, "login_limiter", None)


def _rate_limit_signup(request: Request) -> None:
    limiter = _client_limiter(request)
    if limiter is None:
        return
    retry_after = limiter.consume(current_client_ip() or "unknown")
    if retry_after is not None:
        raise APIError(
            429,
            "too_many_signup_attempts",
            "Too many sign-up attempts; try again shortly",
            {"retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


@router.post("", response_model=UserOut, status_code=201)
def register(
    request: Request,
    body: UserRegister,
    response: Response,
    session: Session = Depends(get_session),
) -> UserOut:
    """Create an account.

    The account is signed in immediately unless the deployment requires an
    administrator to approve new accounts first.
    """

    settings = request.app.state.settings
    if not settings.registration_enabled:
        raise APIError(
            403,
            "registration_disabled",
            "This server is not accepting new accounts",
        )

    _rate_limit_signup(request)

    user = create_user(
        session,
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        password=body.password,
        is_admin=False,
        is_active=not settings.require_admin_approval,
    )
    add_audit(
        session,
        action="user.register",
        outcome="accepted",
        owner_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"email": user.email, "active": bool(user.is_active)},
    )
    session.commit()

    log_event(
        "user.register",
        action="user.register",
        outcome="success",
        owner_id=user.id,
        client_ip=current_client_ip(),
    )

    if not user.is_active:
        return UserOut(**user_to_dict(user))

    # Sign the new account in so it does not have to type its password
    # twice.  The cookies are the same ones the sign-in endpoint sets.
    issue_session(request, response, user.id)
    return UserOut(**user_to_dict(user))


@router.get("/me", response_model=UserOut)
def read_me(
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
    _limited: None = Depends(rate_limit),
) -> UserOut:
    """Return the signed-in account."""

    account = get_user(session, owner)
    if account is None:  # pragma: no cover - defensive
        raise APIError(404, "user_not_found", "Account not found")
    return UserOut(**user_to_dict(account))


@router.patch("/me", response_model=UserOut)
def update_me(
    request: Request,
    body: UserProfileUpdate,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
    _limited: None = Depends(rate_limit),
) -> UserOut:
    """Change the signed-in account's own details."""

    account = get_user(session, owner)
    if account is None:  # pragma: no cover - defensive
        raise APIError(404, "user_not_found", "Account not found")

    if body.password is not None:
        # Changing the password needs the current one, so a stolen cookie
        # cannot be used to lock the owner out.
        if not body.current_password or not _password_matches(
            account, body.current_password
        ):
            raise APIError(
                403,
                "invalid_credentials",
                "The current password is not correct",
            )
        set_password(session, account, body.password)

    if body.email is not None:
        email = validate_email(body.email)
        existing = find_by_email(session, email)
        if existing is not None and existing.id != account.id:
            raise APIError(
                409,
                "email_taken",
                "An account with this email address already exists",
            )
        account.email = email

    if body.first_name is not None:
        account.first_name = validate_name(body.first_name, "First name")
    if body.last_name is not None:
        account.last_name = validate_name(body.last_name, "Last name")

    account.updated_at = utcnow_iso()
    add_audit(
        session,
        action="user.update",
        outcome="accepted",
        owner_id=account.id,
        target_type="user",
        target_id=account.id,
    )
    session.commit()
    return UserOut(**user_to_dict(account))


@router.get("", response_model=list[UserAdminOut])
def admin_list_users(
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
    _limited: None = Depends(rate_limit),
) -> list[UserAdminOut]:
    """List every account.  Administrators only."""

    results: list[UserAdminOut] = []
    for account in list_users(session):
        payload = user_to_dict(account)
        results.append(
            UserAdminOut(
                **payload,
                updated_at=account.updated_at,
                usage=user_usage(session, account.id),
            )
        )
    return results


@router.get("/{user_id}", response_model=UserAdminOut)
def admin_get_user(
    user_id: str,
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
    _limited: None = Depends(rate_limit),
) -> UserAdminOut:
    """Return one account.  Administrators only."""

    account = get_user(session, user_id)
    if account is None:
        raise APIError(404, "user_not_found", f"Account {user_id!r} not found")
    return UserAdminOut(
        **user_to_dict(account),
        updated_at=account.updated_at,
        usage=user_usage(session, account.id),
    )


@router.patch("/{user_id}", response_model=UserAdminOut)
def admin_update_user(
    request: Request,
    user_id: str,
    body: UserAdminUpdate,
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
    _limited: None = Depends(rate_limit),
) -> UserAdminOut:
    """Change an account.  Administrators only."""

    account = get_user(session, user_id)
    if account is None:
        raise APIError(404, "user_not_found", f"Account {user_id!r} not found")

    if body.is_admin is False and account.id == owner:
        raise APIError(
            400,
            "cannot_demote_self",
            "An administrator cannot remove their own administrator rights",
        )
    if body.is_active is False and account.id == owner:
        raise APIError(
            400,
            "cannot_deactivate_self",
            "An administrator cannot deactivate their own account",
        )

    if body.password is not None:
        set_password(session, account, body.password)
    if body.first_name is not None:
        account.first_name = validate_name(body.first_name, "First name")
    if body.last_name is not None:
        account.last_name = validate_name(body.last_name, "Last name")
    if body.is_active is not None:
        account.is_active = body.is_active
    if body.is_admin is not None:
        account.is_admin = body.is_admin

    account.updated_at = utcnow_iso()
    add_audit(
        session,
        action="user.admin_update",
        outcome="accepted",
        owner_id=owner,
        target_type="user",
        target_id=account.id,
        details={
            "is_active": bool(account.is_active),
            "is_admin": bool(account.is_admin),
        },
    )
    session.commit()
    return UserAdminOut(
        **user_to_dict(account),
        updated_at=account.updated_at,
        usage=user_usage(session, account.id),
    )


def _password_matches(account, password: str) -> bool:
    return verify_password_hash(password, account.password_hash)
