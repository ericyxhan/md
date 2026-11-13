#!/usr/bin/env bash
# Set the administrator account's password.
#
# The password is stored as a scrypt hash in .env and the plaintext is never
# written to disk.  The plain WEB_PASSWORD entry is removed, so the secret
# file holds only the hash.
#
# The administrator is the account the lab used before accounts existed, so
# setting this keeps the current sign-in working.
#
# Usage:
#   ./set-admin-password.sh              # generate a strong password and print it
#   ./set-admin-password.sh 'my phrase'  # use a given password
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$SERVICE_DIR/.." && pwd)"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: $VENV_PYTHON not found; the hash helper needs the api venv" >&2
    exit 1
fi

password="${1:-}"
if [[ -z "$password" ]]; then
    password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
    generated=1
else
    generated=0
fi

if [[ ${#password} -lt 12 ]]; then
    echo "ERROR: the password must be at least 12 characters" >&2
    exit 1
fi

# Pass the password through the environment so no shell quoting can mangle it.
export MD_ADMIN_PASSWORD="$password"
hash="$(cd "$SERVICE_DIR/api" && "$VENV_PYTHON" -c "
import os
import sys

sys.path.insert(0, '.')
from app.passwords import hash_password

print(hash_password(os.environ['MD_ADMIN_PASSWORD']))
")"
unset MD_ADMIN_PASSWORD

# Rewrite .env: drop the plaintext entries and set the hash.
#
# The hash is single-quoted because a scrypt hash contains '$' separators,
# and compose interpolates '$' in an unquoted value.
MD_NEW_HASH="$hash" python3 - "$SERVICE_DIR/.env" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
new_hash = os.environ["MD_NEW_HASH"]
if "'" in new_hash:
    raise SystemExit("ERROR: the hash contains a quote and cannot be quoted safely")

lines = path.read_text().splitlines()
kept: list[str] = []
for line in lines:
    if line.startswith("WEB_PASSWORD="):
        continue
    if line.startswith("WEB_PASSWORD_HASH="):
        continue
    if line.startswith("ADMIN_PASSWORD_HASH="):
        continue
    kept.append(line)

# Append the hash, keeping the file's simple KEY=VALUE shape.
kept.append("")
kept.append("# The administrator account's password, stored as a scrypt hash.")
kept.append(f"ADMIN_PASSWORD_HASH='{new_hash}'")

path.write_text("\n".join(kept) + "\n")
path.chmod(0o600)
PY

echo "[set-admin-password] the hash is written to $SERVICE_DIR/.env"

# Apply the new hash to the stored account.
#
# The hash in .env is only the *configured* password: the api leaves an
# administrator's stored hash alone once one is set, so that a password
# changed from the account page survives a restart.  That means writing
# .env on its own would not change the password anybody can sign in with --
# the stored hash is the authoritative one.  Update it here.
#
# The update runs inside the api container, as the service account, so the
# database keeps the ownership the api expects and the container can reach
# the file even when the stack is down.
#
# The hash reaches the container through the service's own environment: the
# api service declares ADMIN_PASSWORD_HASH, and compose reads the .env file
# that was just rewritten.  Passing it through the shell instead would not
# work -- compose does not forward the caller's environment into the
# container.
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    if docker compose --env-file "$SERVICE_DIR/contract.env" \
        --env-file "$SERVICE_DIR/.env" \
        -f "$SERVICE_DIR/compose.yml" -p md-service \
        run --rm --no-deps -T api python - <<'PY'
import os
import sys

sys.path.insert(0, "/app")

from app.db import create_db_engine
from app.settings import get_settings
from app.timeutils import utcnow_iso
from sqlalchemy import text

new_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
if not new_hash:
    raise SystemExit("ERROR: ADMIN_PASSWORD_HASH is not set in the container")

settings = get_settings()
engine = create_db_engine(settings)

with engine.begin() as connection:
    admin = connection.execute(
        text(
            "SELECT id, email FROM users "
            "WHERE is_admin = 1 ORDER BY created_at ASC LIMIT 1"
        )
    ).first()

    if admin is None:
        # No administrator account yet.  The migration creates it from the
        # hash in .env on the next start, so there is nothing to update.
        print("no administrator account yet; the migration will create it")
    else:
        connection.execute(
            text(
                "UPDATE users SET password_hash = :hash, updated_at = :updated "
                "WHERE id = :id"
            ),
            {"hash": new_hash, "updated": utcnow_iso(), "id": admin[0]},
        )
        print(f"the stored hash for {admin[1]} was replaced")
PY
    then
        echo "[set-admin-password] the stored account was updated"
    else
        echo "ERROR: the stored account was not updated." >&2
        echo "       The hash is in .env, but the account still has the old" >&2
        echo "       password.  Set it from the account page in the console." >&2
        exit 1
    fi

    # Restart the API so it picks up the new configuration.
    if docker compose --env-file "$SERVICE_DIR/contract.env" \
        --env-file "$SERVICE_DIR/.env" \
        -f "$SERVICE_DIR/compose.yml" -p md-service \
        up -d api >/dev/null 2>&1; then
        echo "[set-admin-password] the api service was restarted"
    else
        echo "WARNING: the api service could not be restarted" >&2
    fi
else
    echo "WARNING: docker is not available, so the stored account was not updated." >&2
    echo "         The hash is in .env; the account still has the old password." >&2
    exit 1
fi

echo
if [[ "$generated" -eq 1 ]]; then
    echo "==============================================="
    echo " New administrator password (shown once):"
    echo
    echo "   $password"
    echo
    echo " Store it in your password manager now."
    echo "==============================================="
else
    echo "The new password is in effect."
fi
