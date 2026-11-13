"""Move the pre-accounts data layout into the per-account layout.

Before accounts existed the data root held one flat tree::

    uploads/<file_id>/<name>
    jobs/<job_id>/
    prep/<prep_job_id>/

Every account now owns its own tree::

    users/<owner_id>/uploads/<file_id>/<name>
    users/<owner_id>/jobs/<job_id>/
    users/<owner_id>/prep/<prep_job_id>/

The database already knows which account owns what, so this script moves
the directories and rewrites the stored storage keys to match.  It is
idempotent: anything already in the new layout is left alone, so it can be
run again after a partial failure.

Run it inside the api container, where the data root and the database are
mounted at the paths the service uses::

    docker compose -f service/compose.yml run --rm --no-deps api \
        python /app/scripts/migrate_user_data.py

Use ``--dry-run`` first to see what would move.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from pathlib import Path


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _database_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise SystemExit(
            f"ERROR: only SQLite databases are supported, got {database_url!r}"
        )
    return Path(database_url[len(prefix) :])


def _move(source: Path, target: Path) -> bool:
    """Move a directory, refusing to overwrite something that is there."""

    if not source.exists():
        return False
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would move without touching anything",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("DATABASE_URL", ""),
        help="the database URL (defaults to DATABASE_URL)",
    )
    parser.add_argument(
        "--data-root",
        default=os.environ.get("DATA_ROOT", ""),
        help="the data root (defaults to DATA_ROOT)",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="a dotenv file to read DATABASE_URL and DATA_ROOT from",
    )
    arguments = parser.parse_args(argv)

    env: dict[str, str] = {}
    if arguments.env_file:
        env = _read_env_file(Path(arguments.env_file))

    database_url = arguments.database or env.get("DATABASE_URL", "")
    data_root = arguments.data_root or env.get("DATA_ROOT", "")
    if not database_url or not data_root:
        raise SystemExit(
            "ERROR: DATABASE_URL and DATA_ROOT are required "
            "(pass them as options or set them in the environment)"
        )

    root = Path(data_root).expanduser().resolve()
    database = _database_path(database_url)
    if not database.is_file():
        raise SystemExit(f"ERROR: database not found: {database}")

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    moved_files = 0
    moved_jobs = 0
    moved_prep = 0

    try:
        files = connection.execute(
            "SELECT id, owner_id, storage_key FROM files"
        ).fetchall()
        for row in files:
            key = row["storage_key"]
            if key.startswith("users/"):
                continue
            parts = key.split("/")
            if len(parts) != 3 or parts[0] != "uploads":
                continue
            file_id = parts[1]
            source = root / "uploads" / file_id
            target = root / "users" / row["owner_id"] / "uploads" / file_id
            if not source.exists():
                continue
            if not arguments.dry_run:
                _move(source, target)
                connection.execute(
                    "UPDATE files SET storage_key = ? WHERE id = ?",
                    (
                        f"users/{row['owner_id']}/uploads/{file_id}/{parts[2]}",
                        row["id"],
                    ),
                )
            moved_files += 1

        jobs = connection.execute("SELECT id, owner_id FROM jobs").fetchall()
        for row in jobs:
            source = root / "jobs" / row["id"]
            target = root / "users" / row["owner_id"] / "jobs" / row["id"]
            if not source.exists():
                continue
            if not arguments.dry_run:
                _move(source, target)
            moved_jobs += 1

        prep_jobs = connection.execute(
            "SELECT id, owner_id FROM prep_jobs"
        ).fetchall()
        for row in prep_jobs:
            source = root / "prep" / row["id"]
            target = root / "users" / row["owner_id"] / "prep" / row["id"]
            if not source.exists():
                continue
            if not arguments.dry_run:
                _move(source, target)
            moved_prep += 1

        if not arguments.dry_run:
            connection.commit()
    finally:
        connection.close()

    verb = "would move" if arguments.dry_run else "moved"
    print(
        f"[migrate-user-data] {verb} {moved_files} upload(s), "
        f"{moved_jobs} job workspace(s), and {moved_prep} preparation "
        f"workspace(s) under {root / 'users'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
