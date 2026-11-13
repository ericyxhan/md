"""Operational hooks: capacity checks and retention cleanup.

Job creation uses :func:`check_queue_limit` and :func:`ensure_disk_capacity`.
Retention is opt-in (``RETENTION_DAYS=0`` keeps everything) and is intended to
run as an offline administrative task, for example from cron while the API is
idle.  It deletes terminal jobs older than the retention window together with
their SQLite rows and workspace; active jobs are never touched.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db import write_transaction
from ..errors import APIError
from ..models import Job
from ..settings import Settings
from ..storage import LocalStorage, StorageError
from ..timeutils import to_iso
from .audit import add_audit

TERMINAL_STATUSES = ("completed", "failed", "canceled")


@dataclass
class CleanupResult:
    jobs_removed: int = 0
    bytes_freed: int = 0
    orphan_workspaces_removed: int = 0
    orphan_bytes_freed: int = 0
    dry_run: bool = False

    @property
    def total_bytes_freed(self) -> int:
        return self.bytes_freed + self.orphan_bytes_freed


def disk_free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def ensure_disk_capacity(
    settings: Settings,
    storage: LocalStorage,
    *,
    required_bytes: int = 0,
) -> None:
    """Reject new work when the data filesystem is below the reserve."""

    storage.root.mkdir(parents=True, exist_ok=True)
    free = disk_free_bytes(storage.root)
    if free - required_bytes < settings.min_free_disk_bytes:
        raise APIError(
            507,
            "insufficient_storage",
            "The data filesystem does not have enough free space",
            {
                "free_bytes": free,
                "required_bytes": required_bytes,
                "reserve_bytes": settings.min_free_disk_bytes,
            },
        )


def check_queue_limit(
    session: Session, owner_id: str, settings: Settings
) -> None:
    """Reject a new job when the owner already has the maximum queued."""

    queued = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.owner_id == owner_id, Job.status == "queued")
    )
    if queued is not None and queued >= settings.max_queued_jobs_per_owner:
        raise APIError(
            429,
            "queue_limit_exceeded",
            "Too many queued jobs for this owner",
            {
                "queued": queued,
                "limit": settings.max_queued_jobs_per_owner,
            },
        )


def _tree_size(path: Path) -> int:
    """Return the total size of regular files below ``path``."""

    if not path.is_dir():
        return 0
    total = 0
    for directory, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [
            name
            for name in dirnames
            if not (Path(directory) / name).is_symlink()
        ]
        for filename in filenames:
            candidate = Path(directory) / filename
            if candidate.is_symlink():
                continue
            try:
                total += candidate.stat().st_size
            except OSError:
                continue
    return total


def cleanup_expired_jobs(
    session_factory: sessionmaker[Session],
    storage: LocalStorage,
    settings: Settings,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
) -> CleanupResult:
    """Delete terminal jobs and workspaces older than ``retention_days``."""

    result = CleanupResult(dry_run=dry_run)
    if settings.retention_days <= 0:
        return result

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    cutoff = to_iso(reference - timedelta(days=settings.retention_days))

    session = session_factory()
    try:
        candidates = list(
            session.execute(
                select(Job.id, Job.owner_id).where(
                    Job.status.in_(TERMINAL_STATUSES),
                    Job.completed_at.is_not(None),
                    Job.completed_at < cutoff,
                )
            ).all()
        )
    finally:
        session.close()

    for job_id, owner_id in candidates:
        try:
            root = storage.job_root(owner_id, job_id)
        except StorageError:
            continue
        size = _tree_size(root)

        session = session_factory()
        try:
            with write_transaction(session):
                job = session.get(Job, job_id)
                if (
                    job is None
                    or job.status not in TERMINAL_STATUSES
                    or job.completed_at is None
                    or job.completed_at >= cutoff
                ):
                    continue
                if not dry_run:
                    add_audit(
                        session,
                        action="job.retention_delete",
                        outcome="deleted",
                        owner_id=job.owner_id,
                        target_type="job",
                        target_id=job.id,
                        details={
                            "retention_days": settings.retention_days,
                        },
                    )
                    session.delete(job)
                result.jobs_removed += 1
                result.bytes_freed += size
        finally:
            session.close()

        if not dry_run:
            storage.remove_tree(root)

    return result


def cleanup_orphan_workspaces(
    storage: LocalStorage,
    settings: Settings,
    *,
    now: float | None = None,
    dry_run: bool = False,
) -> CleanupResult:
    """Remove abandoned temporary workspaces and partial uploads."""

    result = CleanupResult(dry_run=dry_run)
    reference = now if now is not None else time.time()
    cutoff = reference - settings.orphan_workspace_hours * 3600

    def _is_stale(path: Path) -> bool:
        try:
            return path.stat().st_mtime < cutoff
        except OSError:
            return False

    # Each account has its own tree, so the temporary workspaces are found
    # one account at a time.
    if storage.users.is_dir():
        for owner_dir in storage.users.iterdir():
            if not owner_dir.is_dir() or owner_dir.is_symlink():
                continue
            jobs_dir = owner_dir / "jobs"
            if not jobs_dir.is_dir():
                continue
            for entry in jobs_dir.iterdir():
                if not (
                    entry.name.startswith(".") and entry.name.endswith(".tmp")
                ):
                    continue
                if not _is_stale(entry):
                    continue
                size = _tree_size(entry)
                result.orphan_workspaces_removed += 1
                result.orphan_bytes_freed += size
                if not dry_run:
                    storage.remove_tree(entry)

            uploads_dir = owner_dir / "uploads"
            if not uploads_dir.is_dir():
                continue
            for entry in uploads_dir.rglob("*.part"):
                if entry.is_symlink() or not entry.is_file() or not _is_stale(entry):
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    continue
                result.orphan_workspaces_removed += 1
                result.orphan_bytes_freed += size
                if not dry_run:
                    try:
                        entry.unlink()
                    except OSError:
                        pass

    return result
