#!/usr/bin/env bash
# Full end-to-end launch of the MD service stack.
#
# Stops every existing instance (docker containers + leftover host processes),
# rebuilds all images, then brings every service back up through the per-service
# launch scripts in dependency order.
#
# Usage:
#   ./launch-all.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "================================================================"
echo "[launch-all] FULL STACK LAUNCH — project '$PROJECT_NAME'"
echo "================================================================"

# 0. Refuse to start a deployment whose shared values have drifted apart, or
#    whose host prerequisites are missing.  Everything after this point
#    assumes the contract holds.
echo
echo "--- Step 0: preflight ---"
if ! "$SCRIPT_DIR/preflight.sh"; then
    echo "[launch-all] preflight failed; not starting the stack" >&2
    exit 1
fi

# 1. Stop everything that might already be running.
echo
echo "--- Step 1: stop all existing instances ---"
"$SCRIPT_DIR/stop-all.sh"

# 2. Build all images that have Dockerfiles (api, web, worker, prep-worker).
echo
echo "--- Step 2: build all service images ---"
"${COMPOSE[@]}" build

# 3. Launch services in dependency order.
echo
echo "--- Step 3: launch services in dependency order ---"

echo ">>> launching api (includes migrate) ..."
"$SCRIPT_DIR/launch-api.sh"

echo ">>> launching web ..."
"$SCRIPT_DIR/launch-web.sh"

echo ">>> launching caddy (edge proxy) ..."
"$SCRIPT_DIR/launch-caddy.sh"

echo ">>> launching worker ..."
"$SCRIPT_DIR/launch-worker.sh"

echo ">>> launching prep-worker ..."
"$SCRIPT_DIR/launch-prep-worker.sh"

# 4. Final status.
echo
echo "--- Step 4: final stack status ---"
"${COMPOSE[@]}" ps

echo
echo "================================================================"
echo "[launch-all] FULL STACK UP — project '$PROJECT_NAME'"
echo "  API:        http://127.0.0.1:${MD_API_PORT} (internal, via caddy)"
echo "  Web (SPA):  http://127.0.0.1:${MD_EDGE_PORT}/"
echo "  Caddy edge: http://127.0.0.1:${MD_EDGE_PORT} (loopback only)"
echo
echo "  Publish it publicly with:"
echo "    systemctl --user start md-funnel.service"
echo "================================================================"
