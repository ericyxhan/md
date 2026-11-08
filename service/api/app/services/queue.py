"""Queue queries shared by the public and internal APIs."""

from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..models import Job


def queue_position(session: Session, job: Job) -> int | None:
    """Return the 1-based queue position, or ``None`` for non-queued jobs."""

    if job.status != "queued":
        return None
    earlier = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.status == "queued",
            or_(
                Job.queued_at < job.queued_at,
                and_(
                    Job.queued_at == job.queued_at,
                    Job.created_at < job.created_at,
                ),
                and_(
                    Job.queued_at == job.queued_at,
                    Job.created_at == job.created_at,
                    Job.id < job.id,
                ),
            ),
        )
    )
    return int(earlier or 0) + 1


def queued_job_ids(session: Session, limit: int = 100) -> list[str]:
    """Return queued job IDs in claim order (oldest enqueue first)."""

    statement = (
        select(Job.id)
        .where(Job.status == "queued")
        .order_by(Job.queued_at.asc(), Job.created_at.asc(), Job.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())
