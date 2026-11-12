#!/usr/bin/env bash
# Launch the web SPA service.
#
# Builds the React app and serves it from nginx on port 80 (internal to compose,
# proxied by caddy).
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[launch-web] building + starting web ..."
"${COMPOSE[@]}" up -d --build web

echo "[launch-web] web container status:"
"${COMPOSE[@]}" ps web
