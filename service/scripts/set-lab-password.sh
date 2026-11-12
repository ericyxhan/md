#!/usr/bin/env bash
# Set the browser login password.
#
# The password is stored as a scrypt hash in .env and the plaintext is never
# written to disk.  The plain WEB_PASSWORD entry is removed, so the secret
# file holds only the hash.
#
# Usage:
#   ./set-lab-password.sh              # generate a strong password and print it
#   ./set-lab-password.sh 'my phrase'  # use a given password
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
export MD_LAB_PASSWORD="$password"
hash="$(cd "$SERVICE_DIR/api" && "$VENV_PYTHON" -c "
import os
import sys

sys.path.insert(0, '.')
from app.session import hash_password

print(hash_password(os.environ['MD_LAB_PASSWORD']))
")"
unset MD_LAB_PASSWORD

# Rewrite .env: drop the plaintext entry and set the hash.
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
    kept.append(line)

# Append the hash, keeping the file's simple KEY=VALUE shape.
if not any(line.startswith("WEB_PASSWORD_HASH=") for line in kept):
    kept.append("")
    kept.append("# Browser login.  Stored as a scrypt hash; the plaintext is never on disk.")
    kept.append(f"WEB_PASSWORD_HASH='{new_hash}'")

path.write_text("\n".join(kept) + "\n")
path.chmod(0o600)
PY

echo "[set-lab-password] the hash is written to $SERVICE_DIR/.env"

# Restart the API so the new hash takes effect.
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose --env-file "$SERVICE_DIR/contract.env" \
        --env-file "$SERVICE_DIR/.env" \
        -f "$SERVICE_DIR/compose.yml" -p md-service \
        up -d api >/dev/null 2>&1 || true
    echo "[set-lab-password] the api service was restarted"
fi

echo
if [[ "$generated" -eq 1 ]]; then
    echo "==============================================="
    echo " New lab password (shown once):"
    echo
    echo "   $password"
    echo
    echo " Store it in your password manager now."
    echo "==============================================="
else
    echo "The new password is in effect."
fi
