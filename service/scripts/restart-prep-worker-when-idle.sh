#!/usr/bin/env bash
# Wait for an in-flight prep job to finish, then restart the prep worker so it
# picks up the current image.
#
# This exists because restarting the prep worker mid-job SIGKILLs the running
# packmol process, and the API has no stale-prep-job reaper, so the job would
# be orphaned in "running" forever.  Waiting for it to reach a terminal state
# first is the safe way to roll a new worker image out.
#
# Usage:
#   ./restart-prep-worker-when-idle.sh [JOB_ID]
#
# With no JOB_ID the most recent non-terminal prep job is used.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

JOB_ID="${1:-}"
POLL_INTERVAL="${POLL_INTERVAL:-20}"
MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-86400}"
API_CONTAINER="${API_CONTAINER:-md-service-api-1}"

# Read one prep job row as "status|phase|percent".
# NOTE: `-i` is required so the heredoc script reaches python inside the
# container; without it docker does not forward stdin and the command
# silently produces no output.
read_job() {
  docker exec -i "$API_CONTAINER" python3 - "$1" <<'PY' 2>/dev/null || true
import sqlite3
import sys

job_id = sys.argv[1]
conn = sqlite3.connect("/db/app.db")
conn.row_factory = sqlite3.Row
if job_id:
    row = conn.execute(
        "SELECT id, status, phase, progress_percent FROM prep_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
else:
    row = conn.execute(
        "SELECT id, status, phase, progress_percent FROM prep_jobs "
        "WHERE status IN ('queued', 'claimed', 'running') "
        "ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
if row is None:
    print("MISSING||")
else:
    print(f"{row['id']}|{row['status']}|{row['phase']}|{row['progress_percent']}")
PY
}

if [[ -z "$JOB_ID" ]]; then
  ROW="$(read_job "")"
  JOB_ID="${ROW%%|*}"
  if [[ -z "$JOB_ID" || "$JOB_ID" == "MISSING" ]]; then
    echo "[wait-idle] no prep job is currently running; restarting prep worker now."
    "${COMPOSE[@]}" up -d prep-worker
    exit 0
  fi
fi

echo "[wait-idle] watching prep job $JOB_ID (poll every ${POLL_INTERVAL}s, max ${MAX_WAIT_SECONDS}s)"

STARTED=$SECONDS
LAST_STATUS=""
READ_FAILURES=0
while true; do
  ROW="$(read_job "$JOB_ID")"
  if [[ -z "$ROW" ]]; then
    # An empty result means the read itself failed (container restarting,
    # transient error).  It does NOT mean the job finished.  Retry before
    # concluding anything.
    READ_FAILURES=$(( READ_FAILURES + 1 ))
    if (( READ_FAILURES < 5 )); then
      sleep "$POLL_INTERVAL"
      continue
    fi
    echo "[wait-idle] could not read the job after ${READ_FAILURES} attempts; giving up without restarting." >&2
    exit 1
  fi
  READ_FAILURES=0

  if [[ "$ROW" == "MISSING||" ]]; then
    echo "[wait-idle] job row disappeared; restarting prep worker."
    break
  fi

  IFS='|' read -r _id status phase percent <<<"$ROW"

  if [[ "$status" != "$LAST_STATUS" ]]; then
    echo "[wait-idle] status=$status phase=${phase:-—} percent=${percent:-—}"
    LAST_STATUS="$status"
  fi

  case "$status" in
    completed|failed|canceled)
      echo "[wait-idle] job reached '$status' after $(( SECONDS - STARTED ))s."
      break
      ;;
  esac

  if (( SECONDS - STARTED > MAX_WAIT_SECONDS )); then
    echo "[wait-idle] gave up after ${MAX_WAIT_SECONDS}s; restarting prep worker anyway." >&2
    break
  fi

  sleep "$POLL_INTERVAL"
done

echo "[wait-idle] restarting prep worker ..."
"${COMPOSE[@]}" up -d prep-worker
"${COMPOSE[@]}" ps prep-worker
echo "[wait-idle] done."
