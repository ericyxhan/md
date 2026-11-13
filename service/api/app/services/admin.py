"""Cross-account views for the administrator console.

Every function here returns rows for every account, joined to the owning
user.  They exist so an administrator can see the platform as a whole —
the whole queue, the whole audit trail — and nothing in this module is
used by the per-account API surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from ..errors import APIError
from ..models import Artifact, AuditEvent, FileRecord, Job, User, Worker
from ..settings import Settings
from .jobs import _decode_cursor, _encode_cursor, job_to_dict
from .maintenance import _tree_size, disk_free_bytes


def list_platform_jobs(
    session: Session,
    *,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[tuple[Job, User]], str | None]:
    """List jobs across every account, joined to the owning user.

    Ordering matches the per-account listing (newest first, keyset-
    paginated on (created_at, id)).
    """

    statement = select(Job, User).options(selectinload(Job.stages)).join(
        User, Job.owner_id == User.id
    )
    if status is not None:
        statement = statement.where(Job.status == status)
    if cursor is not None:
        created_at, job_id = _decode_cursor(cursor)
        statement = statement.where(
            (Job.created_at < created_at)
            | ((Job.created_at == created_at) & (Job.id < job_id))
        )
    statement = statement.order_by(Job.created_at.desc(), Job.id.desc()).limit(
        limit + 1
    )

    rows = list(session.execute(statement).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1][0])
    return [(job, owner) for job, owner in rows], next_cursor


def job_to_admin_dict(
    session: Session,
    job: Job,
    owner: User,
    *,
    queue_positions: Mapping[str, int] | None = None,
    now: str,
) -> dict:
    """Serialize one job with its owning account for the admin console."""

    data = job_to_dict(session, job, queue_positions=queue_positions)
    data["owner_id"] = owner.id
    data["owner_email"] = owner.email
    data["owner_first_name"] = owner.first_name
    data["owner_last_name"] = owner.last_name
    data["stale"] = _is_stale(job, now)
    return data


def _is_stale(job: Job, now: str) -> bool:
    """A claimed/running/canceling job that is going nowhere.

    Either a cancellation was requested and the worker never acknowledged
    it, or the worker claimed the job and its lease expired without a
    heartbeat — the reaper will fail it with ``worker_lost`` shortly.
    """

    if job.status not in ("claimed", "running", "canceling"):
        return False
    if job.cancel_requested:
        return True
    return (
        job.lease_expires_at is not None
        and job.lease_expires_at < now
    )


def platform_queue_counts(session: Session) -> dict[str, int]:
    statement = select(Job.status, func.count(Job.id)).group_by(Job.status)
    return {status: int(count) for status, count in session.execute(statement)}


def system_dashboard(
    session: Session,
    settings: Settings,
    storage_root: Path,
    *,
    now: str,
) -> dict:
    """Everything the admin health page shows, in one query round trip each."""

    migration = None
    try:
        migration = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        reachable = True
    except Exception:
        reachable = False

    counts = {
        "jobs": int(session.scalar(select(func.count()).select_from(Job)) or 0),
        "users": int(session.scalar(select(func.count()).select_from(User)) or 0),
        "files": int(session.scalar(select(func.count()).select_from(FileRecord)) or 0),
        "audit_events": int(
            session.scalar(select(func.count()).select_from(AuditEvent)) or 0
        ),
        "artifacts": int(session.scalar(select(func.count()).select_from(Artifact)) or 0),
    }

    artifact_bytes = int(
        session.scalar(select(func.coalesce(func.sum(Artifact.size_bytes), 0))) or 0
    )

    workers = []
    for worker in session.scalars(select(Worker).order_by(Worker.registered_at)).all():
        heartbeat_age = _seconds_between(worker.last_heartbeat_at, now)
        workers.append(
            {
                "id": worker.id,
                "hostname": worker.hostname,
                "gpu_name": worker.gpu_name,
                "version": worker.version,
                "status": worker.status,
                "current_job_id": worker.current_job_id,
                "last_heartbeat_at": worker.last_heartbeat_at,
                "heartbeat_age_seconds": heartbeat_age,
                "stale": heartbeat_age > settings.worker_lease_seconds,
            }
        )

    return {
        "generated_at": now,
        "api_version": "v1",
        "database": {
            "reachable": reachable,
            "migration": str(migration) if migration is not None else None,
            **counts,
            "artifact_bytes": artifact_bytes,
        },
        "data_root": {
            "path": str(storage_root),
            "free_bytes": disk_free_bytes(storage_root),
            "min_free_bytes": settings.min_free_disk_bytes,
            "users_bytes": _tree_size(storage_root / "users"),
        },
        "workers": workers,
        "queue_counts": platform_queue_counts(session),
    }


def _seconds_between(earlier: str, now: str) -> float:
    from datetime import datetime

    try:
        then = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00"))
        return max(0.0, (current - then).total_seconds())
    except ValueError:
        return 0.0


def list_audit_events(
    session: Session,
    *,
    action: str | None = None,
    outcome: str | None = None,
    owner_id: str | None = None,
    limit: int,
    cursor: str | None,
) -> tuple[list[tuple[AuditEvent, User | None]], str | None]:
    """List the append-only audit trail, newest first.

    Keyset pagination on the autoincrement id, which is monotonic in time.
    The owner join is outer so audit rows written for unauthenticated
    requests (which carry no owner) still appear.
    """

    statement = (
        select(AuditEvent, User)
        .outerjoin(User, AuditEvent.owner_id == User.id)
        .order_by(AuditEvent.id.desc())
    )
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if outcome is not None:
        statement = statement.where(AuditEvent.outcome == outcome)
    if owner_id is not None:
        statement = statement.where(AuditEvent.owner_id == owner_id)
    if cursor is not None:
        try:
            after_id = int(cursor)
        except ValueError as exc:
            raise APIError(400, "invalid_cursor", "Invalid audit cursor") from exc
        statement = statement.where(AuditEvent.id < after_id)
    statement = statement.limit(limit + 1)

    rows = list(session.execute(statement).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = str(rows[-1][0].id)
    return rows, next_cursor
