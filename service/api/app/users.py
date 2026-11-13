"""User accounts: registration, authentication, and the admin bootstrap.

Every row in this service owns data.  The account id is the ``owner_id``
used by jobs, files, prep jobs, workflows, and audit events, so the
ownership checks across the API stay a single equality test.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .errors import APIError
from .models import FileRecord, Job, PrepJob, User
from .passwords import hash_password, password_problem, verify_password_hash
from .settings import Settings
from .timeutils import utcnow_iso

MAX_EMAIL_LENGTH = 255
MAX_NAME_LENGTH = 100

# Deliberately permissive: the address only has to be well formed enough to
# be deliverable.  Deep validation belongs to the confirmation mail, not to
# the signup form.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def normalize_email(email: str) -> str:
    """Return the canonical form of an address.

    Addresses are compared case-insensitively, so they are stored lowercased
    and the uniqueness constraint does the rest.
    """

    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        raise APIError(400, "invalid_email", "Email address is required")
    if len(normalized) > MAX_EMAIL_LENGTH:
        raise APIError(
            400,
            "invalid_email",
            f"Email address must be at most {MAX_EMAIL_LENGTH} characters",
        )
    if not _EMAIL_RE.match(normalized):
        raise APIError(
            400,
            "invalid_email",
            "Enter a valid email address",
        )
    return normalized


def validate_name(value: str, label: str) -> str:
    name = (value or "").strip()
    if not name:
        raise APIError(400, "invalid_name", f"{label} is required")
    if len(name) > MAX_NAME_LENGTH:
        raise APIError(
            400,
            "invalid_name",
            f"{label} must be at most {MAX_NAME_LENGTH} characters",
        )
    if any(ord(character) < 32 for character in name):
        raise APIError(
            400,
            "invalid_name",
            f"{label} must not contain control characters",
        )
    return name


def validate_password(password: str) -> None:
    problem = password_problem(password)
    if problem is not None:
        raise APIError(400, "weak_password", problem)


def get_user(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def find_by_email(session: Session, email: str) -> User | None:
    return session.scalar(
        select(User).where(User.email == normalize_email(email))
    )


def create_user(
    session: Session,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    is_admin: bool = False,
    is_active: bool = True,
    password_hash: str | None = None,
) -> User:
    """Create an account and return the stored row.

    The email is validated and normalized here so every caller — signup
    form, admin tool, bootstrap — writes the same canonical value.
    """

    normalized = validate_email(email)
    first = validate_name(first_name, "First name")
    last = validate_name(last_name, "Last name")

    if password_hash is None:
        validate_password(password)
        password_hash = hash_password(password)

    if find_by_email(session, normalized) is not None:
        raise APIError(
            409,
            "email_taken",
            "An account with this email address already exists",
        )

    now = utcnow_iso()
    user = User(
        id=str(uuid.uuid4()),
        email=normalized,
        first_name=first,
        last_name=last,
        password_hash=password_hash,
        is_admin=is_admin,
        is_active=is_active,
        created_at=now,
        updated_at=now,
        last_login_at=None,
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    """Return the active account matching the credentials.

    A missing account and a wrong password are indistinguishable to the
    caller: both mean "no such user".  The comparison itself is
    constant-time inside :func:`verify_password_hash`.
    """

    user = find_by_email(session, email)
    if user is None or not user.is_active:
        # Still spend the hashing work so a missing account and a wrong
        # password take the same time and cannot be told apart.
        verify_password_hash(password, _DUMMY_HASH)
        return None
    if not verify_password_hash(password, user.password_hash):
        return None
    return user


def record_login(session: Session, user: User) -> None:
    now = utcnow_iso()
    user.last_login_at = now
    user.updated_at = now


def set_password(session: Session, user: User, password: str) -> None:
    validate_password(password)
    user.password_hash = hash_password(password)
    user.updated_at = utcnow_iso()


def user_to_dict(user: User) -> dict[str, Any]:
    """Serialize an account for the API.

    The password hash is never part of the payload.
    """

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_admin": bool(user.is_admin),
        "is_active": bool(user.is_active),
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


def list_users(session: Session) -> list[User]:
    return list(
        session.scalars(
            select(User).order_by(User.created_at.asc(), User.id.asc())
        ).all()
    )


def user_usage(session: Session, user_id: str) -> dict[str, int]:
    """Return the row counts that belong to one account."""

    def _count(model, column) -> int:
        value = session.scalar(
            select(func.count()).select_from(model).where(column == user_id)
        )
        return int(value or 0)

    return {
        "jobs": _count(Job, Job.owner_id),
        "files": _count(FileRecord, FileRecord.owner_id),
        "prep_jobs": _count(PrepJob, PrepJob.owner_id),
    }


# A well-formed hash of a value nobody can guess.  It is only used to keep
# the timing of a failed login constant when the account does not exist.
_DUMMY_HASH = hash_password("no-such-account")


def find_admin(session: Session) -> User | None:
    """Return the administrator account, if there is one."""

    return session.scalar(
        select(User).where(User.is_admin == True).order_by(  # noqa: E712
            User.created_at.asc()
        )
    )


def ensure_admin(session: Session, settings: Settings) -> User:
    """Return the administrator account, creating it when it is missing.

    The administrator is the account the lab used before accounts existed:
    the shared password in ``WEB_PASSWORD_HASH`` becomes that account's
    password, and every row that used the old ``local`` owner moves to it.
    The migration that moves the rows runs first; this function only
    guarantees that an administrator exists so the bearer token and the
    admin console have somebody to act as.
    """

    admin = find_admin(session)
    if admin is None:
        admin = create_user(
            session,
            email=settings.admin_email,
            first_name=settings.admin_first_name,
            last_name=settings.admin_last_name,
            password="",
            is_admin=True,
            password_hash=_admin_password_hash(settings),
        )
        session.commit()
        return admin

    if not admin.password_hash:
        # The account exists but has no password yet — the deployment was
        # upgraded and the lab password has not been applied to it.  An
        # administrator who has since set a password is left alone.
        stored = _admin_password_hash(settings)
        if stored:
            admin.password_hash = stored
            admin.updated_at = utcnow_iso()
            session.commit()
    return admin


def _admin_password_hash(settings: Settings) -> str:
    """Return the hash to store for the administrator.

    A deployment that kept the lab password as plaintext gets it hashed
    once, here, and never again.
    """

    if settings.admin_password_hash:
        return settings.admin_password_hash
    if settings.web_password:
        return hash_password(settings.web_password)
    return ""
