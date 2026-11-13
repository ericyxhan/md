"""Signed browser sessions for the web frontend.

Machine clients keep using the static ``SERVICE_API_TOKEN`` bearer token.  A
browser never receives that token: it exchanges an account email address and
password at ``POST /api/v1/session`` for a short-lived, HMAC-signed,
HttpOnly cookie.

Sessions are stateless.  Rotating ``WEB_SESSION_SECRET`` (or, for a deployment
without a dedicated secret, ``SERVICE_API_TOKEN``) invalidates every existing
session.  The cookie value contains no secrets and is safe to hand to the
browser; the signature makes it unforgeable.

The subject of a session is the account id, which is also the ``owner_id``
of everything that account creates.

Cross-site request forgery uses the double-submit pattern: login also sets a
readable ``md_csrf`` cookie and the frontend echoes it in ``X-CSRF-Token`` on
every mutating request.  Combined with ``SameSite=Lax`` this is sufficient for
the single-origin deployment.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from .errors import APIError
from .passwords import hash_password, verify_password_hash
from .settings import Settings

SESSION_COOKIE = "md_session"
CSRF_COOKIE = "md_csrf"
CSRF_HEADER = "X-CSRF-Token"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "MUTATING_METHODS",
    "SESSION_COOKIE",
    "Session",
    "decode_session",
    "encode_session",
    "hash_password",
    "issue_session",
    "session_from_request",
    "session_secret",
    "verify_csrf",
    "verify_password",
]


@dataclass(frozen=True)
class Session:
    """A decoded, verified browser session."""

    subject: str
    issued_at: int
    expires_at: int
    nonce: str

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.subject,
            "issued_at": _iso(self.issued_at),
            "expires_at": _iso(self.expires_at),
        }


def _iso(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).digest()
    return _b64encode(digest)


def session_secret(settings: Settings) -> str:
    """Return the HMAC key, falling back to the service token."""

    return settings.web_session_secret or settings.service_api_token


def sessions_configured(settings: Settings) -> bool:
    """Return whether browser sign-in is enabled on this deployment."""

    return settings.web_login_enabled


def encode_session(
    secret: str,
    subject: str,
    *,
    ttl_seconds: int,
    now: int | None = None,
) -> tuple[str, Session]:
    issued = int(time.time() if now is None else now)
    session = Session(
        subject=subject,
        issued_at=issued,
        expires_at=issued + max(60, int(ttl_seconds)),
        nonce=secrets.token_urlsafe(12),
    )
    payload = json.dumps(
        {
            "sub": session.subject,
            "iat": session.issued_at,
            "exp": session.expires_at,
            "nonce": session.nonce,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        f"{_b64encode(payload)}.{_signature(secret, payload)}",
        session,
    )


def decode_session(
    secret: str,
    token: str,
    *,
    now: int | None = None,
) -> Session | None:
    """Return the session if the signature and expiry are valid."""

    if not secret or not token:
        return None
    try:
        payload_b64, provided_signature = token.split(".", 1)
        payload = _b64decode(payload_b64)
    except (ValueError, TypeError):
        return None

    expected_signature = _signature(secret, payload)
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None

    try:
        data = json.loads(payload)
        session = Session(
            subject=str(data["sub"]),
            issued_at=int(data["iat"]),
            expires_at=int(data["exp"]),
            nonce=str(data["nonce"]),
        )
    except (ValueError, KeyError, TypeError):
        return None

    current = int(time.time() if now is None else now)
    if session.expires_at <= current:
        return None
    return session


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------


def verify_password(settings: Settings, password: str) -> bool:
    """Constant-time check against the configured plaintext or hash.

    This is the deployment-wide lab password.  Accounts have their own
    hashes in the ``users`` table; see :mod:`app.passwords`.
    """

    if settings.web_password_hash:
        return verify_password_hash(password, settings.web_password_hash)

    if not settings.web_password:
        return False
    return hmac.compare_digest(password, settings.web_password)


def issue_session(request, response, owner: str) -> Session:
    """Set the session and CSRF cookies for an account.

    Both the sign-in endpoint and the sign-up endpoint use this, so a new
    account ends up with exactly the same cookies as a returning one.
    """

    settings = request.app.state.settings
    token, session = encode_session(
        session_secret(settings),
        owner,
        ttl_seconds=settings.web_session_ttl_seconds,
    )
    csrf_token = secrets.token_urlsafe(32)
    options = {
        "path": "/",
        "secure": settings.web_cookie_secure,
        "samesite": "lax",
    }

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
    return session


def verify_csrf(request) -> None:
    """Reject a mutating cookie-authenticated request without a CSRF token."""

    if request.method.upper() not in MUTATING_METHODS:
        return
    provided = request.headers.get(CSRF_HEADER)
    expected = request.cookies.get(CSRF_COOKIE)
    if (
        not provided
        or not expected
        or not hmac.compare_digest(provided, expected)
    ):
        raise APIError(
            403,
            "csrf_failed",
            "Missing or invalid CSRF token",
        )


def session_from_request(request) -> Session | None:
    settings = request.app.state.settings
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return decode_session(session_secret(settings), token)
