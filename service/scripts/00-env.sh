#!/usr/bin/env bash
# Shared environment for the launch/stop/check scripts.
#
# Source this from any script in this directory:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/00-env.sh"
#
# The shared contract (ports, service account, mount paths, route prefixes)
# lives in service/contract.env and is committed.  Deployment secrets live in
# service/.env, which is layered on top of it.  Compose reads both, in that
# order, so a secret in .env always wins over a contract default.
#
set -euo pipefail

# Resolve the directory containing this script so the scripts work no matter
# what the current working directory is.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$SERVICE_DIR/.." && pwd)"

# Canonical deployment is the docker-compose project in service/compose.yml.
COMPOSE_FILE="$SERVICE_DIR/compose.yml"
CONTRACT_FILE="$SERVICE_DIR/contract.env"
ENV_FILE="$SERVICE_DIR/.env"
PROJECT_NAME="md-service"

# Require the contract file to exist; it is the single source of truth for
# every shared value.
if [[ ! -f "$CONTRACT_FILE" ]]; then
    echo "ERROR: contract file not found: $CONTRACT_FILE" >&2
    exit 1
fi

# Require the env file to exist so we never launch with missing secrets.
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE" >&2
    echo "  Copy service/.env.example to service/.env and fill in the values." >&2
    exit 1
fi

# Load the contract into the environment so the shell scripts can use the
# same values as compose and Caddy.
set -a
# shellcheck disable=SC1090
source "$CONTRACT_FILE"
set +a

# Compose command prefix used by every script.  The contract is read first so
# its values are available for interpolation, then the deployment env
# overrides them.
COMPOSE=(docker compose --env-file "$CONTRACT_FILE" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$PROJECT_NAME")

echo "[env] project=$PROJECT_NAME contract=$CONTRACT_FILE env=$ENV_FILE"

# read_env KEY [DEFAULT]
#
# Read one key from the deployment env file.  The file is in compose's dotenv
# format, which is not necessarily valid shell, so it is never sourced; only
# the key that is asked for is read.
read_env() {
    local key="$1" default="${2:-}"
    local value
    value="$(sed -n "s/^${key}=//p" "$ENV_FILE" 2>/dev/null | tail -n 1)"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    printf '%s' "${value:-$default}"
}
