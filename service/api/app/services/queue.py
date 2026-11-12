"""Queue queries shared by the public and internal APIs."""

from __future__ import annotations

from collections.abc import Iterable

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


def queue_positions(session: Session, jobs: Iterable[Job]) -> dict[str, int]:
    """Return the queue position of every queued job in *jobs*.

    This is the batched form of :func:`queue_position`: the queue order is
    ``(queued_at, created_at, id)``, so one window-function query ranks the
    whole queue instead of running a COUNT per job.  Listing a page of jobs
    otherwise issues one extra query per row.

    Jobs whose ``queued_at`` is missing are skipped; the caller falls back to
    :func:`queue_position` for those, which keeps the two functions in
    agreement.
    """

    queued = [
        job
        for job in jobs
        if job.status == "queued" and job.queued_at is not None
    ]
    if not queued:
        return {}

    ranked = (
        select(
            Job.id.label("id"),
            func.row_number()
            .over(
                order_by=(
                    Job.queued_at.asc(),
                    Job.created_at.asc(),
                    Job.id.asc(),
                )
            )
            .label("position"),
        )
        .where(Job.status == "queued", Job.queued_at.is_not(None))
        .cte("queued_jobs")
    )
    job_ids = [job.id for job in queued]
    rows = session.execute(
        select(ranked.c.id, ranked.c.position).where(
            ranked.c.id.in_(job_ids)
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def queued_job_ids(session: Session, limit: int = 100) -> list[str]:
    """Return queued job IDs in claim order (oldest enqueue first)."""

    statement = (
        select(Job.id)
        .where(Job.status == "queued")
        .order_by(Job.queued_at.asc(), Job.created_at.asc(), Job.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())
