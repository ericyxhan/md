"""Database engine, session handling, and SQLite pragmas."""

from __future__ import annotations

import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from .settings import Settings


class Base(DeclarativeBase):
    """Declarative base for all service models."""


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _ensure_sqlite_parent(url: str) -> None:
    """Create the parent directory for a file-backed SQLite database."""

    prefix = "sqlite:///"
    if not url.startswith(prefix) or url.endswith(":memory:"):
        return
    path_text = url[len(prefix) :]
    if not path_text or path_text.startswith(":memory:"):
        return
    path = Path(path_text)
    if path.is_absolute():
        path.parent.mkdir(parents=True, exist_ok=True)


def ensure_database_directory(settings: Settings) -> None:
    """Create the parent directory for a file-backed SQLite database."""

    _ensure_sqlite_parent(settings.database_url)


def create_db_engine(settings: Settings) -> Engine:
    """Create a configured SQLAlchemy engine.

    SQLite uses a single shared engine with ``check_same_thread=False`` because
    FastAPI runs synchronous endpoints in a thread pool.  The API is still one
    process and all write transitions are serialized by ``WRITE_LOCK``.
    """

    url = settings.database_url

    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if _is_sqlite(url):
        kwargs["connect_args"] = {
            "check_same_thread": False,
            "timeout": settings.db_busy_timeout_ms / 1000.0,
        }
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool

    engine = create_engine(url, **kwargs)

    if _is_sqlite(url):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute(
                    f"PRAGMA busy_timeout = {int(settings.db_busy_timeout_ms)}"
                )
                cursor.execute("PRAGMA synchronous = NORMAL")
            finally:
                cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a short-lived session."""

    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


# All state-changing transitions in the single API process take this lock in
# addition to a database transaction.  SQLite serializes writers anyway; the
# lock makes claim/cancel/retry deterministic and avoids lock-upgrade errors.
WRITE_LOCK = threading.RLock()


@contextmanager
def write_transaction(session: Session) -> Iterator[Session]:
    """Run a short state-changing transaction while holding the write lock."""

    with WRITE_LOCK:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def immediate_transaction(session: Session) -> Iterator[Session]:
    """Run a transitioning transaction with a SQLite ``BEGIN IMMEDIATE``.

    Claim, cancel, and retry must not race with another writer that selects the
    same row.  ``WRITE_LOCK`` serializes threads in this single API process and
    ``BEGIN IMMEDIATE`` asks SQLite for the write lock up front.  Callers must
    enter this context before the session has executed its first statement.
    """

    with WRITE_LOCK:
        try:
            session.execute(text("BEGIN IMMEDIATE"))
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

