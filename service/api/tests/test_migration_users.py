"""The upgrade from the shared owner to real accounts.

The migration is the one moment where a deployment's existing data changes
owner, so it is tested against a database that really holds the rows the
pre-accounts deployment had.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.settings import Settings
from conftest import ADMIN_OWNER_ID, API_DIR

LEGACY_OWNER_ID = "local"


def _upgrade_to(database_url: str, revision: str) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, revision)


def _rows(database_url: str, sql: str) -> list[tuple]:
    path = Path(database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(path) as connection:
        return connection.execute(sql).fetchall()


def _legacy_database(tmp_path: Path) -> str:
    """Build the database a deployment had before accounts existed."""

    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    _upgrade_to(database_url, "0008")

    # The rows the old deployment held, owned by the shared lab owner.
    connection = sqlite3.connect(tmp_path / "app.db")
    try:
        connection.execute(
            "INSERT INTO jobs (id, owner_id, name, status, spec_json, "
            "config_toml, input_mode, attempt, cancel_requested, "
            "created_at, updated_at) "
            "VALUES ('job-1', ?, 'old job', 'queued', '{}', '', 'complex', "
            "0, 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (LEGACY_OWNER_ID,),
        )
        connection.execute(
            "INSERT INTO files (id, owner_id, original_name, content_type, "
            "size_bytes, sha256, storage_key, created_at) "
            "VALUES ('file-1', ?, 'complex.pdb', 'chemical/x-pdb', 10, '', "
            "'uploads/file-1/complex.pdb', '2026-01-01T00:00:00Z')",
            (LEGACY_OWNER_ID,),
        )
        connection.execute(
            "INSERT INTO prep_jobs (id, owner_id, type, status, request_json, "
            "cancel_requested, created_at, updated_at) "
            "VALUES ('prep-1', ?, 'system_prep', 'queued', '{}', 0, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (LEGACY_OWNER_ID,),
        )
        connection.execute(
            "INSERT INTO workflows (id, owner_id, name, source_file_id, "
            "source_type, created_at, updated_at) "
            "VALUES ('workflow-1', ?, 'old workflow', 'file-1', 'complex', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (LEGACY_OWNER_ID,),
        )
        connection.execute(
            "INSERT INTO audit_events (owner_id, action, outcome, created_at) "
            "VALUES (?, 'job.create', 'accepted', '2026-01-01T00:00:00Z')",
            (LEGACY_OWNER_ID,),
        )
        connection.commit()
    finally:
        connection.close()

    return database_url


def test_the_shared_owner_becomes_the_administrator(tmp_path: Path) -> None:
    database_url = _legacy_database(tmp_path)

    _upgrade_to(database_url, "head")

    # Every row that belonged to the shared owner now belongs to the
    # administrator, so the existing work stays reachable.
    assert _rows(
        database_url, "SELECT owner_id FROM jobs"
    ) == [(ADMIN_OWNER_ID,)]
    assert _rows(
        database_url, "SELECT owner_id FROM files"
    ) == [(ADMIN_OWNER_ID,)]
    assert _rows(
        database_url, "SELECT owner_id FROM prep_jobs"
    ) == [(ADMIN_OWNER_ID,)]
    assert _rows(
        database_url, "SELECT owner_id FROM workflows"
    ) == [(ADMIN_OWNER_ID,)]
    assert _rows(
        database_url, "SELECT owner_id FROM audit_events"
    ) == [(ADMIN_OWNER_ID,)]


def test_the_administrator_account_is_created(tmp_path: Path) -> None:
    database_url = _legacy_database(tmp_path)

    _upgrade_to(database_url, "head")

    accounts = _rows(
        database_url,
        "SELECT id, email, first_name, last_name, is_admin, is_active "
        "FROM users",
    )
    assert len(accounts) == 1
    account_id, email, first_name, last_name, is_admin, is_active = accounts[0]
    assert account_id == ADMIN_OWNER_ID
    assert email == "admin@lattice.local"
    assert first_name == "Lab"
    assert last_name == "Administrator"
    assert is_admin == 1
    assert is_active == 1


def test_the_administrator_takes_the_configured_password(
    tmp_path: Path, monkeypatch
) -> None:
    """The lab password keeps working after the upgrade."""

    database_url = _legacy_database(tmp_path)
    monkeypatch.setenv("ADMIN_EMAIL", "ada@example.com")
    monkeypatch.setenv("ADMIN_FIRST_NAME", "Ada")
    monkeypatch.setenv("ADMIN_LAST_NAME", "Lovelace")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "scrypt$16384$8$1$aaaa$bbbb")

    _upgrade_to(database_url, "head")

    assert _rows(
        database_url,
        "SELECT email, first_name, last_name, password_hash FROM users",
    ) == [
        (
            "ada@example.com",
            "Ada",
            "Lovelace",
            "scrypt$16384$8$1$aaaa$bbbb",
        )
    ]


def test_a_plaintext_lab_password_is_hashed_during_the_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    database_url = _legacy_database(tmp_path)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("WEB_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("WEB_PASSWORD", "the old lab password")

    _upgrade_to(database_url, "head")

    stored = _rows(database_url, "SELECT password_hash FROM users")[0][0]
    assert stored.startswith("scrypt$")
    assert "the old lab password" not in stored

    from app.passwords import verify_password_hash

    assert verify_password_hash("the old lab password", stored)


def test_the_upgrade_is_reversible(tmp_path: Path) -> None:
    """Downgrading puts the rows back on the shared owner."""

    database_url = _legacy_database(tmp_path)
    _upgrade_to(database_url, "head")

    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "0008")

    assert _rows(database_url, "SELECT owner_id FROM jobs") == [
        (LEGACY_OWNER_ID,)
    ]
    assert _rows(database_url, "SELECT owner_id FROM files") == [
        (LEGACY_OWNER_ID,)
    ]
    assert "users" not in {
        row[0] for row in _rows(
            database_url, "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def test_a_fresh_database_creates_the_accounts_table(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    _upgrade_to(database_url, "head")

    tables = {
        row[0]
        for row in _rows(
            database_url, "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "users" in tables
