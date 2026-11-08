"""Append-only job event log."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import JobEvent
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
