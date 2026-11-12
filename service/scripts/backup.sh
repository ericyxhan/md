#!/usr/bin/env bash
# Back up the control plane and the job data root.
#
# The database is copied with SQLite's online backup API.  That is safe to
# run against a live WAL database and always produces a consistent snapshot,
# so the service does not have to be stopped first.
#
# The data root is a plain tarball.  A job that happens to be writing at that
# moment can leave a partial artifact behind, which is recoverable; losing
# the control plane is not.  For that reason a failed data copy is reported
# but does not discard the database backup.
#
# Job artifacts are written by the containers as their own service account
# with owner-only permissions, so a complete data copy needs root.  Run this
# from a root crontab to avoid an interactive sudo prompt.
#
# Usage:
#   ./backup.sh [BACKUP_DIR]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_FILE="$SCRIPT_DIR/../.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: env file not found: $ENV_FILE" >&2
    exit 1
fi

read_env() {
    # Last assignment wins, matching compose's behaviour for repeated keys.
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1 | sed 's/^["'\'']//; s/["'\'']$//'
}

DB_DIR="$(read_env HOST_DB_DIR)"
DATA_DIR="$(read_env HOST_DATA_DIR)"
BACKUP_DIR="${1:-$(read_env BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/md-service-backups}"
RETENTION_DAYS="$(read_env BACKUP_RETENTION_DAYS)"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if ! command -v sqlite3 >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: need sqlite3 (apt-get install -y sqlite3) or python3" >&2
    exit 1
fi

DB_FILE="$DB_DIR/app.db"
if [[ ! -f "$DB_FILE" ]]; then
    echo "ERROR: database not found: $DB_FILE" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_BACKUP="$BACKUP_DIR/app-$STAMP.db"

if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB_FILE" ".backup '$DB_BACKUP'"
else
    # Same online backup API, without needing the CLI package installed.
    python3 - "$DB_FILE" "$DB_BACKUP" <<'PY'
import sqlite3
import sys

source_path, target_path = sys.argv[1], sys.argv[2]
with sqlite3.connect(source_path) as source:
    with sqlite3.connect(target_path) as target:
        source.backup(target)
PY
fi
echo "[backup] database -> $DB_BACKUP"

if [[ -d "$DATA_DIR" ]]; then
    ERROR_LOG="$BACKUP_DIR/tar-errors.log"
    DATA_ARCHIVE="$BACKUP_DIR/data-$STAMP.tgz"
    if tar -C "$DATA_DIR" -czf "$DATA_ARCHIVE" . 2>"$ERROR_LOG"; then
        echo "[backup] data     -> $DATA_ARCHIVE"
        rm -f "$ERROR_LOG"
    elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        # Something in the tree is not readable by this account.  A container
        # runs as root and can read all of it, so the copy is still complete.
        echo "[backup] data root is not fully readable; copying through a container"
        if docker run --rm -v "$DATA_DIR:/data:ro" alpine \
            tar -C /data -czf - . >"$DATA_ARCHIVE" 2>"$ERROR_LOG"; then
            echo "[backup] data     -> $DATA_ARCHIVE (via container)"
            rm -f "$ERROR_LOG"
        else
            echo "[backup] WARNING: data copy incomplete; see $ERROR_LOG" >&2
        fi
    else
        echo "[backup] WARNING: data copy incomplete; see $ERROR_LOG" >&2
    fi
else
    echo "[backup] WARNING: data root not found: $DATA_DIR" >&2
fi

find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+$RETENTION_DAYS" -print -delete
