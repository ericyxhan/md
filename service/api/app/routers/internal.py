"""Internal worker protocol.

These routes are authenticated with ``X-Worker-Token`` instead of the public
bearer token and are hidden from the public OpenAPI document.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas_internal import (
    ClaimRequest,
    ClaimResponse,
    FinishRequest,
    FinishResponse,
    ProgressRequest,
    ProgressResponse,
    StageUpdateRequest,
    StageUpdateResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
)
from ..security import require_worker
from ..services import lifecycle

router = APIRouter(
    prefix="/internal/v1",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_worker)],
)


@router.post(
    "/workers/heartbeat",
    response_model=WorkerHeartbeatResponse,
)
def heartbeat(
    request: Request,
    body: WorkerHeartbeatRequest,
    session: Session = Depends(get_session),
) -> WorkerHeartbeatResponse:
    return lifecycle.heartbeat(
        session, request.app.state.settings, body
    )


@router.post(
    "/jobs/claim",
    response_model=ClaimResponse,
    responses={204: {"description": "No queued jobs"}},
)
def claim(
    request: Request,
    body: ClaimRequest,
    session: Session = Depends(get_session),
):
    result = lifecycle.claim(
        session,
        request.app.state.settings,
        request.app.state.storage,
        body,
    )
    if result is None:
        return Response(status_code=204)
    return result


@router.post(
    "/jobs/{job_id}/progress",
    response_model=ProgressResponse,
)
def progress(
    job_id: str,
    request: Request,
    body: ProgressRequest,
    session: Session = Depends(get_session),
) -> ProgressResponse:
    return lifecycle.update_progress(
        session, request.app.state.settings, job_id, body
    )


@router.post(
    "/jobs/{job_id}/stage",
    response_model=StageUpdateResponse,
)
def stage(
    job_id: str,
    request: Request,
    body: StageUpdateRequest,
    session: Session = Depends(get_session),
) -> StageUpdateResponse:
    return lifecycle.update_stage(
        session, request.app.state.settings, job_id, body
    )


@router.post(
    "/jobs/{job_id}/finish",
    response_model=FinishResponse,
)
def finish(
    job_id: str,
    request: Request,
    body: FinishRequest,
    session: Session = Depends(get_session),
) -> FinishResponse:
    result = lifecycle.finish(
        session,
        request.app.state.storage,
        job_id,
        body,
    )
    return FinishResponse.model_validate(result)
