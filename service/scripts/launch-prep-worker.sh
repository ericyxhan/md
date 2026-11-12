#!/usr/bin/env bash
# Launch the prep worker.
#
# Claims membrane-embedding jobs from the internal API and runs packmol-memgen.
# Depends on the api container being healthy. Uses the existing image for speed;
# use launch-all.sh to rebuild everything.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[launch-prep-worker] starting prep-worker ..."
"${COMPOSE[@]}" up -d prep-worker

echo "[launch-prep-worker] prep-worker container status:"
"${COMPOSE[@]}" ps prep-worker
