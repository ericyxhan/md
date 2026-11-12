"""Append-only job event log."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import JobEvent, PrepEvent
from ..timeutils import utcnow_iso


def add_event(
    session: Session,
    job_id: str,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> JobEvent:
    event = JobEvent(
        job_id=job_id,
        type=event_type,
        message=message,
        data_json=json.dumps(data, sort_keys=True) if data is not None else None,
        created_at=utcnow_iso(),
    )
    session.add(event)
    return event


def add_prep_event(
    session: Session,
    prep_job_id: str,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> PrepEvent:
    """Append an event to a system-preparation job's log.

    Prep jobs live in their own table, so their activity is recorded here
    rather than in ``job_events`` (which is keyed by MD job id).
    """
    event = PrepEvent(
        prep_job_id=prep_job_id,
        type=event_type,
        message=message,
        data_json=json.dumps(data, sort_keys=True) if data is not None else None,
        created_at=utcnow_iso(),
    )
    session.add(event)
    return event
