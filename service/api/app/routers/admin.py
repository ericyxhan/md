"""Cross-account administrator views.

Three endpoints: the whole queue across the deployment (``/jobs``), the
health of the service and data store (``/system``), and the append-only
audit trail (``/audit``).  Everything here requires an administrator; the
per-account routers must never expose these.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..schemas import (
    AdminAuditListOut,
    AdminAuditOut,
    AdminJobListOut,
    AdminSystemOut,
)
from ..security import require_admin
from ..services.admin import (
    job_to_admin_dict,
    list_audit_events,
    list_platform_jobs,
    system_dashboard,
)
from ..services.jobs import _JOB_STATUSES
from ..services.queue import queue_positions
from ..timeutils import utcnow_iso

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs", response_model=AdminJobListOut)
def admin_list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminJobListOut:
    """Every job on the platform, newest first.

    Joins the owning account and flags the ones going nowhere (cancellation
    requested and never acknowledged, or a worker lease that expired without
    a heartbeat).
    """

    if status is not None and status not in _JOB_STATUSES:
        raise APIError(
            400,
            "invalid_status",
            f"Unknown job status {status!r}; expected one of {', '.join(_JOB_STATUSES)}",
        )

    rows, next_cursor = list_platform_jobs(
        session, status=status, limit=limit, cursor=cursor
    )
    jobs = [job for job, _ in rows]
    positions = queue_positions(session, jobs) if jobs else {}
    now = utcnow_iso()
    return AdminJobListOut(
        items=[
            job_to_admin_dict(
                session,
                job,
                owner_user,
                queue_positions=positions,
                now=now,
            )
            for job, owner_user in rows
        ],
        next_cursor=next_cursor,
    )


@router.get("/system", response_model=AdminSystemOut)
def admin_system(
    request: Request,
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminSystemOut:
    """Health of the service and its data store.

    Covers what ``/readyz`` checks (database, migrations, data root) plus
    the business state an administrator needs: how much data the platform
    holds, what is left on disk, how many jobs of each status are in
    flight, and whether the worker is still heartbeating.
    """

    settings = request.app.state.settings
    storage = request.app.state.storage
    now = utcnow_iso()
    return AdminSystemOut.model_validate(
        system_dashboard(session, settings, Path(storage.root), now=now)
    )


@router.get("/audit", response_model=AdminAuditListOut)
def admin_audit(
    action: str | None = Query(default=None, max_length=64),
    outcome: str | None = Query(default=None, max_length=24),
    owner_id: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    owner: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> AdminAuditListOut:
    """The audit trail, newest first.

    Keyset-paginated by row id.  Use ``?action=`` and ``?outcome=`` to
    narrow to one kind of event, and ``?owner_id=`` for one account.
    """

    rows, next_cursor = list_audit_events(
        session,
        action=action,
        outcome=outcome,
        owner_id=owner_id,
        limit=limit,
        cursor=cursor,
    )
    return AdminAuditListOut(
        items=[
            AdminAuditOut(
                id=event.id,
                created_at=event.created_at,
                owner_id=event.owner_id,
                owner_email=user.email if user is not None else None,
                action=event.action,
                outcome=event.outcome,
                target_type=event.target_type,
                target_id=event.target_id,
                remote_addr=event.remote_addr,
                request_id=event.request_id,
            )
            for event, user in rows
        ],
        next_cursor=next_cursor,
    )
