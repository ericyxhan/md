"""Server-sent events for job state and progress.

The stream is intentionally read-only and keeps no database session open while
sleeping.  Each poll opens a short-lived session, reads a bounded page of
events, emits a compact progress snapshot when it changed, and closes the
session before the next sleep.  A terminal job emits its remaining events,
one final snapshot, and an ``end`` event so clients know reconnection is not
required.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..models import Job
from .jobs import list_events

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


def _snapshot(job: Job) -> dict[str, Any]:
    error = None
    if job.error_code is not None:
        error = {
            "code": job.error_code,
            "message": job.error_message or job.error_code,
        }
    return {
        "id": job.id,
        "status": job.status,
        "phase": job.phase,
        "current_stage": job.current_stage,
        "attempt": job.attempt,
        "step": job.progress_step,
        "total_steps": job.progress_total_steps,
        "percent": job.progress_percent,
        "progress_updated_at": job.progress_updated_at,
        "updated_at": job.updated_at,
        "error": error,
    }


def format_sse(
    data: Any,
    *,
    event: str | None = None,
    event_id: int | None = None,
) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event is not None:
        lines.append(f"event: {event}")
    payload = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def job_event_stream(
    session_factory: sessionmaker[Session],
    job_id: str,
    *,
    after_id: int = 0,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
    page_size: int = 200,
) -> Iterator[str]:
    """Yield SSE frames until the job is terminal or the client disconnects."""

    last_event_id = max(0, after_id)
    last_snapshot: dict[str, Any] | None = None
    last_keepalive = time.monotonic()

    while True:
        session = session_factory()
        try:
            job = session.get(Job, job_id)
            if job is None:
                yield format_sse(
                    {
                        "code": "job_not_found",
                        "message": f"Job {job_id!r} was not found",
                    },
                    event="error",
                )
                return
            events = list_events(
                session,
                job,
                limit=page_size,
                after_id=last_event_id or None,
            )
            snapshot = _snapshot(job)
            terminal = job.status in TERMINAL_STATUSES
        finally:
            session.close()

        emitted = False
        for event in events:
            last_event_id = max(last_event_id, int(event["id"]))
            yield format_sse(
                event,
                event="job",
                event_id=int(event["id"]),
            )
            emitted = True

        if snapshot != last_snapshot:
            last_snapshot = snapshot
            yield format_sse(snapshot, event="progress")
            emitted = True

        if terminal:
            # Drain any remaining pages before closing the stream.
            if len(events) >= page_size:
                continue
            yield format_sse({"status": snapshot["status"]}, event="end")
            return

        now = time.monotonic()
        if emitted:
            last_keepalive = now
        elif now - last_keepalive >= heartbeat_seconds:
            yield ": keep-alive\n\n"
            last_keepalive = now

        time.sleep(poll_seconds)
