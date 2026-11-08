"""Artifact validation, listing, and log access.

Worker completion reports are validated here: paths stay inside the job
workspace, symlinks are rejected, and sizes come from the filesystem.  Public
downloads resolve database rows by ID; the API never accepts a filesystem path
from a caller.
"""

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import APIError
from ..models import Artifact, Job
from ..storage import LocalStorage, StorageError
from ..timeutils import to_iso, utcnow_iso

_MEDIA_TYPE_RE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$"
)
_DOWNLOAD_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

ARTIFACT_KINDS = frozenset(
    {
        "config",
        "log",
        "state",
        "checkpoint",
        "trajectory",
        "structure",
        "metadata",
    }
)

# Logs written by the worker before any artifact metadata is reported.
KNOWN_LOG_PATHS = (
    "logs/worker.log",
    "logs/simulate.stdout",
    "logs/simulate.stderr",
)


@dataclass(frozen=True)
class LogEntry:
    name: str
    relative_path: str
    size_bytes: int
    content_type: str
    updated_at: str


def safe_download_name(value: str) -> str:
    """Return an ASCII-only attachment filename without path components."""

    name = PurePosixPath(value.replace("\\", "/")).name
    name = _DOWNLOAD_NAME_RE.sub("_", name).strip("._")
    return (name or "artifact")[:180]


def _content_type(item: Any, path) -> str:
    guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    supplied = item.content_type
    if supplied and _MEDIA_TYPE_RE.match(supplied):
        return supplied[:128]
    return guessed[:128]


def _artifact_path(storage: LocalStorage, job_id: str, relative_path: str):
    try:
        return storage.job_path(job_id, relative_path)
    except StorageError as exc:
        raise APIError(
            400,
            "invalid_artifact_path",
            f"Artifact path {relative_path!r} is not allowed",
            {"path": relative_path, "reason": str(exc)},
        ) from exc


def _confined_file(
    storage: LocalStorage, job_id: str, relative_path: str
) -> Path:
    """Resolve a stored relative path for a public read.

    The path is database-derived; invalid or missing files are treated as a
    missing resource rather than exposing filesystem details.
    """

    try:
        path = storage.job_path(job_id, relative_path)
    except StorageError as exc:
        raise APIError(
            404,
            "artifact_unavailable",
            "Artifact is no longer available",
        ) from exc
    if not path.is_file():
        raise APIError(
            404,
            "artifact_missing",
            "Artifact file is missing from the workspace",
        )
    return path


def register_artifacts(
    session: Session,
    storage: LocalStorage,
    job: Job,
    artifacts: list[Any],
) -> list[Artifact]:
    """Validate and upsert artifact metadata reported by a worker.

    The caller is responsible for the transaction.  Paths are confined to the
    job workspace, symlinks are rejected, missing files are an error, and the
    size recorded in the database always comes from the filesystem rather than
    from the worker payload.
    """

    stage_names = {stage.name for stage in job.stages}
    registered: list[Artifact] = []
    seen: dict[str, Artifact] = {}
    now = utcnow_iso()

    for item in artifacts:
        if item.stage_name is not None and item.stage_name not in stage_names:
            raise APIError(
                422,
                "invalid_stage",
                f"Stage {item.stage_name!r} does not belong to this job",
                {"available": sorted(stage_names)},
            )

        path = _artifact_path(storage, job.id, item.relative_path)
        if not path.exists():
            raise APIError(
                422,
                "artifact_missing",
                f"Artifact {item.relative_path!r} does not exist",
                {"path": item.relative_path},
            )
        if not path.is_file():
            raise APIError(
                422,
                "artifact_not_file",
                f"Artifact {item.relative_path!r} is not a regular file",
                {"path": item.relative_path},
            )

        size_bytes = path.stat().st_size
        content_type = _content_type(item, path)

        existing = seen.get(item.relative_path)
        if existing is None:
            existing = session.scalar(
                select(Artifact).where(
                    Artifact.job_id == job.id,
                    Artifact.relative_path == item.relative_path,
                )
            )
        if existing is None:
            record = Artifact(
                id=str(uuid.uuid4()),
                job_id=job.id,
                stage_name=item.stage_name,
                kind=item.kind,
                relative_path=item.relative_path,
                size_bytes=size_bytes,
                content_type=content_type,
                created_at=now,
            )
            session.add(record)
        else:
            record = existing
            record.stage_name = item.stage_name
            record.kind = item.kind
            record.size_bytes = size_bytes
            record.content_type = content_type
            record.created_at = now
        seen[item.relative_path] = record
        registered.append(record)

    return registered


# ---------------------------------------------------------------------------
# Public artifact access
# ---------------------------------------------------------------------------


def list_artifacts(
    session: Session,
    job: Job,
    *,
    kind: str | None = None,
    stage_name: str | None = None,
) -> list[Artifact]:
    if kind is not None and kind not in ARTIFACT_KINDS:
        raise APIError(
            400,
            "invalid_artifact_kind",
            f"Unknown artifact kind {kind!r}",
            {"available": sorted(ARTIFACT_KINDS)},
        )
    statement = select(Artifact).where(Artifact.job_id == job.id)
    if kind is not None:
        statement = statement.where(Artifact.kind == kind)
    if stage_name is not None:
        statement = statement.where(Artifact.stage_name == stage_name)
    statement = statement.order_by(Artifact.relative_path.asc())
    return list(session.scalars(statement).all())


def get_artifact(session: Session, job: Job, artifact_id: str) -> Artifact:
    artifact = session.get(Artifact, artifact_id)
    if artifact is None or artifact.job_id != job.id:
        raise APIError(
            404,
            "artifact_not_found",
            f"Artifact {artifact_id!r} was not found",
        )
    return artifact


def artifact_path(storage: LocalStorage, job: Job, artifact: Artifact) -> Path:
    return _confined_file(storage, job.id, artifact.relative_path)


# ---------------------------------------------------------------------------
# Log discovery and tailing
# ---------------------------------------------------------------------------


def _file_metadata(
    storage: LocalStorage, job_id: str, relative_path: str
) -> tuple[Path, os.stat_result] | None:
    try:
        path = storage.job_path(job_id, relative_path)
        stat = path.stat()
    except (StorageError, OSError):
        return None
    if not path.is_file():
        return None
    return path, stat


def _log_entry(
    storage: LocalStorage, job_id: str, relative_path: str
) -> LogEntry | None:
    metadata = _file_metadata(storage, job_id, relative_path)
    if metadata is None:
        return None
    path, stat = metadata
    content_type = mimetypes.guess_type(path.name)[0] or "text/plain"
    updated_at = to_iso(datetime.fromtimestamp(stat.st_mtime, timezone.utc))
    return LogEntry(
        name=relative_path,
        relative_path=relative_path,
        size_bytes=stat.st_size,
        content_type=content_type[:128],
        updated_at=updated_at,
    )


def list_logs(
    session: Session, storage: LocalStorage, job: Job
) -> list[LogEntry]:
    """List worker logs and registered log artifacts inside the workspace.

    The worker log names are a fixed allowlist so a running job can expose its
    logs before the finish report registers artifacts.  Registered ``log``
    artifacts cover logs produced inside ``outputs/``.
    """

    paths: set[str] = set(KNOWN_LOG_PATHS)
    registered = session.scalars(
        select(Artifact).where(
            Artifact.job_id == job.id,
            Artifact.kind == "log",
        )
    ).all()
    paths.update(artifact.relative_path for artifact in registered)

    entries: list[LogEntry] = []
    for relative_path in sorted(paths):
        entry = _log_entry(storage, job.id, relative_path)
        if entry is not None:
            entries.append(entry)
    return entries


def get_log(
    session: Session, storage: LocalStorage, job: Job, name: str
) -> LogEntry:
    """Resolve a log name without accepting an arbitrary path.

    ``name`` is normally the workspace-relative path (for example
    ``logs/worker.log``).  A unique basename is also accepted for convenience.
    """

    entries = list_logs(session, storage, job)
    normalized = name.replace("\\", "/").strip("/")
    for entry in entries:
        if entry.name == normalized:
            return entry
    basename_matches = [
        entry
        for entry in entries
        if PurePosixPath(entry.relative_path).name == normalized
    ]
    if len(basename_matches) == 1:
        return basename_matches[0]
    raise APIError(
        404,
        "log_not_found",
        f"Log {name!r} was not found",
        {"available": [entry.name for entry in entries]},
    )


def log_path(storage: LocalStorage, job: Job, entry: LogEntry) -> Path:
    return _confined_file(storage, job.id, entry.relative_path)


def read_log_tail(
    path: Path,
    *,
    max_bytes: int,
    max_lines: int,
) -> tuple[str, int, bool]:
    """Read a bounded tail without loading the whole file into memory."""

    try:
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        with path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(max_bytes)
    except OSError as exc:
        raise APIError(
            404,
            "log_missing",
            "Log file is missing from the workspace",
        ) from exc

    text = data.decode("utf-8", errors="replace")
    truncated = start > 0
    if truncated:
        newline = text.find("\n")
        if newline != -1:
            text = text[newline + 1 :]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        truncated = True
    content = "\n".join(lines)
    if content:
        content += "\n"
    return content, len(lines), truncated

