"""Migration and SQLite pragma tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text

from app.db import create_db_engine
from app.settings import Settings
from conftest import upgrade_database


def _table_names(database_url: str) -> set[str]:
    path = Path(database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def test_upgrade_from_empty_database_creates_schema(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    upgrade_database(database_url)
    names = _table_names(database_url)
    assert {
        "alembic_version",
        "jobs",
        "job_stages",
        "files",
        "artifacts",
        "job_events",
        "workers",
        "audit_events",
    } <= names


def test_engine_sets_sqlite_pragmas(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        data_root=tmp_path / "data",
    )
    upgrade_database(settings.database_url)
    engine = create_db_engine(settings)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert (
                connection.execute(text("PRAGMA busy_timeout")).scalar() == 5000
            )
    finally:
        engine.dispose()
