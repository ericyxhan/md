#!/usr/bin/env bash
# Stop every running instance of the MD service stack and clean up floating
# containers/images left over from previous sessions.
#
# 1. Stops the docker-compose project (api, web, worker, prep-worker, caddy,
#    migrate) via `docker compose down --remove-orphans`.
# 2. Removes any stopped containers not belonging to the current project
#    (floating containers from earlier sessions).
# 3. Removes dangling images and old untagged test images (md-web:test, etc.).
# 4. Kills any leftover host processes (uvicorn, worker.py, prep_worker.py,
#    caddy, nginx) from running the services directly on the host.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[stop-all] step 1: stopping docker-compose project '$PROJECT_NAME' ..."
"${COMPOSE[@]}" down --remove-orphans --timeout 30 2>/dev/null || true

echo "[stop-all] step 2: removing floating/stopped containers from previous sessions ..."
# List all containers (including stopped) whose names are NOT part of the
# md-service project, then remove them.
FLOATING=$(docker ps -a --filter "name=md-service-" --format "{{.Names}}" 2>/dev/null || true)
ALL_NAMES=$(docker ps -a --format "{{.Names}}" 2>/dev/null || true)
for name in $ALL_NAMES; do
  case "$name" in
    md-service-*) : ;; # skip project containers
    *) 
      echo "  removing floating container: $name"
      docker rm -f "$name" 2>/dev/null || true
      ;;
  esac
done

echo "[stop-all] step 3: removing dangling images ..."
DANGLING=$(docker images -q -f dangling=true 2>/dev/null || true)
if [[ -n "$DANGLING" ]]; then
  echo "$DANGLING" | xargs -r docker rmi -f 2>/dev/null || true
  echo "  removed $(echo "$DANGLING" | wc -l) dangling image(s)"
else
  echo "  (none)"
fi

echo "[stop-all] step 4: removing old untagged test images (md-web:test, api:latest) ..."
for img in md-web:test md-web:test2 md-web:test3 api:latest; do
  if docker inspect "$img" >/dev/null 2>&1; then
    echo "  removing $img"
    docker rmi -f "$img" 2>/dev/null || true
  fi
done

echo "[stop-all] step 5: killing leftover host processes ..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "worker.py" 2>/dev/null || true
pkill -f "prep_worker.py" 2>/dev/null || true
pkill -f "caddy run --config /etc/caddy/Caddyfile" 2>/dev/null || true
pkill -f "nginx: master process" 2>/dev/null || true

sleep 2

echo "[stop-all] remaining listeners on ${MD_EDGE_PORT}/${MD_API_PORT} (if any):"
ss -tlnp 2>/dev/null | grep -E ":(${MD_EDGE_PORT}|${MD_API_PORT})\b" || echo "  (none)"

echo "[stop-all] done."
