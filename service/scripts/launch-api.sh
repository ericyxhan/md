#!/usr/bin/env bash
# Launch the API service (and its migrate dependency).
#
# The API is the backend FastAPI service. `migrate` runs first to bring the DB
# schema to head, then `api` serves uvicorn on port 8000 (internal to compose).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[launch-api] starting migrate + api ..."
"${COMPOSE[@]}" up -d migrate api

echo "[launch-api] api container status:"
"${COMPOSE[@]}" ps api migrate
