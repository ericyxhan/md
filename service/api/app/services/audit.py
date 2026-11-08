"""Persistent audit trail for control-plane mutations.

Audit rows are written in the same transaction as the mutation they describe,
so an accepted action and its audit record commit together.  Authentication
and rate-limit denials are emitted as structured log events instead: they must
not create database work for unauthenticated traffic.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import AuditEvent
from ..observability import current_client_ip, current_request_id
from ..timeutils import utcnow_iso


def add_audit(
    session: Session,
    *,
    action: str,
    outcome: str,
    owner_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one audit row to the caller's current transaction."""

    client_ip = current_client_ip()
    event = AuditEvent(
        request_id=current_request_id(),
        owner_id=owner_id,
        action=action[:64],
        outcome=outcome[:24],
        target_type=target_type[:32] if target_type else None,
        target_id=target_id[:64] if target_id else None,
        details_json=(
            json.dumps(details, sort_keys=True, default=str)
            if details is not None
            else None
        ),
        remote_addr=client_ip[:64] if client_ip else None,
        created_at=utcnow_iso(),
    )
    session.add(event)
    return event
