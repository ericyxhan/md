"""Password hashing for user accounts.

Passwords are stored as self-describing scrypt hashes: the work factors are
part of the hash, so a deployment can raise them later without invalidating
the passwords that are already stored.  The plaintext is never written to
disk, not even inside the hash.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

# Password policy for self-service accounts.  The length is the dominant
# factor; composition rules mostly push people towards predictable patterns.
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    """Return a self-describing scrypt hash for ``password``."""

    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
        f"${_b64encode(salt)}${_b64encode(derived)}"
    )


def verify_password_hash(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored hash.

    Returns ``False`` for any malformed or missing hash instead of raising,
    so a corrupt row can never turn into a crash on the login path.
    """

    if not stored or not password:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


def password_problem(password: str) -> str | None:
    """Return a human-readable reason the password is unacceptable.

    ``None`` means the password is acceptable.
    """

    if not password:
        return "Password is required"
    if len(password) < MIN_PASSWORD_LENGTH:
        return (
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        return (
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long"
        )
    if password.strip() != password:
        return "Password must not start or end with whitespace"
    return None
