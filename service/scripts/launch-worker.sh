#!/usr/bin/env bash
# Launch the simulation worker.
#
# Claims simulation jobs from the internal API and runs OpenMM. Depends on the
# api container being healthy. Uses the existing image (no rebuild) for speed;
# use launch-all.sh to rebuild everything.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[launch-worker] starting worker ..."
"${COMPOSE[@]}" up -d worker

echo "[launch-worker] worker container status:"
"${COMPOSE[@]}" ps worker
