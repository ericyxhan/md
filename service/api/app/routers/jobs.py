"""Public job API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..schemas import (
    ArtifactListOut,
    ArtifactOut,
    EventOut,
    JobCreate,
    JobListOut,
    JobOut,
    JobPlanOut,
    JobValidateRequest,
    LogListOut,
    LogOut,
    LogTailOut,
    RetryRequest,
)
from ..security import require_owner
from ..services.artifacts import (
    artifact_path,
    get_artifact,
    get_log,
    list_artifacts,
    list_logs,
    log_path,
    read_log_tail,
    safe_download_name,
)
from ..services.jobs import (
    create_job,
    get_owned_job,
    job_to_dict,
    list_events,
    list_jobs,
    validate_job,
)
from ..services.lifecycle import cancel_job, retry_job
from ..services.stream import job_event_stream

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _artifact_out(artifact) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        stage_name=artifact.stage_name,
        kind=artifact.kind,
        relative_path=artifact.relative_path,
        name=safe_download_name(artifact.relative_path),
        size_bytes=artifact.size_bytes,
        content_type=artifact.content_type,
        created_at=artifact.created_at,
    )


@router.post("/validate", response_model=JobPlanOut)
def validate(
    request: Request,
    body: JobValidateRequest,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobPlanOut:
    plan, config_toml = validate_job(
        session,
        request.app.state.settings,
        request.app.state.storage,
        body,
        owner,
    )
    return JobPlanOut(valid=True, config_toml=config_toml, plan=plan)


@router.post("", response_model=JobOut, status_code=202)
def create(
    request: Request,
    body: JobCreate,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobOut:
    job = create_job(
        session,
        request.app.state.settings,
        request.app.state.storage,
        body,
        owner,
    )
    return JobOut.model_validate(job_to_dict(session, job))


@router.get("", response_model=JobListOut)
def list_all(
    status: str | None = Query(default=None),
    limit: int = Query(default=20),
    cursor: str | None = Query(default=None),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobListOut:
    jobs, next_cursor = list_jobs(
        session, owner, status=status, limit=limit, cursor=cursor
    )
    return JobListOut(
        items=[JobOut.model_validate(job_to_dict(session, job)) for job in jobs],
        next_cursor=next_cursor,
    )


@router.get("/{job_id}", response_model=JobOut)
def get_one(
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobOut:
    job = get_owned_job(session, owner, job_id)
    return JobOut.model_validate(job_to_dict(session, job))


@router.get("/{job_id}/config", response_class=PlainTextResponse)
def get_config(
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    job = get_owned_job(session, owner, job_id)
    return PlainTextResponse(
        job.config_toml,
        media_type="application/toml",
        headers={
            "Content-Disposition": f'inline; filename="{job.id}-config.toml"'
        },
    )


@router.get("/{job_id}/events", response_model=list[EventOut])
def get_events(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    after_id: int | None = Query(default=None, ge=0),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    job = get_owned_job(session, owner, job_id)
    return [
        EventOut.model_validate(event)
        for event in list_events(session, job, limit=limit, after_id=after_id)
    ]


@router.get("/{job_id}/events/stream")
def stream_events(
    request: Request,
    job_id: str,
    after_id: int | None = Query(default=None, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    owner: str = Depends(require_owner),
):
    """Server-sent events for job events and progress.

    A terminal job sends its remaining events, one final ``progress`` snapshot,
    and an ``end`` event, then closes.  Live jobs stay open with keep-alive
    comments.  Reconnect with ``Last-Event-ID`` (or ``after_id``) to resume.
    """

    session = request.app.state.session_factory()
    try:
        get_owned_job(session, owner, job_id)
    finally:
        session.close()

    cursor = after_id
    if cursor is None and last_event_id:
        try:
            cursor = max(0, int(last_event_id))
        except ValueError:
            cursor = 0

    settings = request.app.state.settings
    stream = job_event_stream(
        request.app.state.session_factory,
        job_id,
        after_id=cursor or 0,
        poll_seconds=settings.event_stream_poll_seconds,
        heartbeat_seconds=settings.event_stream_heartbeat_seconds,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/artifacts", response_model=ArtifactListOut)
def get_artifacts(
    job_id: str,
    kind: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> ArtifactListOut:
    job = get_owned_job(session, owner, job_id)
    artifacts = list_artifacts(session, job, kind=kind, stage_name=stage)
    return ArtifactListOut(items=[_artifact_out(item) for item in artifacts])


@router.get("/{job_id}/artifacts/{artifact_id}")
def download_artifact(
    request: Request,
    job_id: str,
    artifact_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    job = get_owned_job(session, owner, job_id)
    artifact = get_artifact(session, job, artifact_id)
    path = artifact_path(request.app.state.storage, job, artifact)
    return FileResponse(
        path,
        media_type=artifact.content_type or "application/octet-stream",
        filename=safe_download_name(artifact.relative_path),
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{job_id}/logs", response_model=LogListOut)
def get_logs(
    request: Request,
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> LogListOut:
    job = get_owned_job(session, owner, job_id)
    entries = list_logs(session, request.app.state.storage, job)
    return LogListOut(
        items=[
            LogOut(
                name=entry.name,
                relative_path=entry.relative_path,
                size_bytes=entry.size_bytes,
                content_type=entry.content_type,
                updated_at=entry.updated_at,
            )
            for entry in entries
        ]
    )


@router.get("/{job_id}/logs/{name:path}/tail", response_model=LogTailOut)
def tail_log(
    request: Request,
    job_id: str,
    name: str,
    lines: int | None = Query(default=None, ge=1, le=10_000),
    max_bytes: int | None = Query(default=None, ge=1024, le=4 * 1024 * 1024),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> LogTailOut:
    job = get_owned_job(session, owner, job_id)
    entry = get_log(session, request.app.state.storage, job, name)
    settings = request.app.state.settings
    content, line_count, truncated = read_log_tail(
        log_path(request.app.state.storage, job, entry),
        max_bytes=min(
            max_bytes or settings.log_tail_max_bytes,
            settings.log_tail_max_bytes,
        ),
        max_lines=lines or settings.log_tail_default_lines,
    )
    return LogTailOut(
        name=entry.name,
        relative_path=entry.relative_path,
        content=content,
        lines=line_count,
        truncated=truncated,
        size_bytes=entry.size_bytes,
    )


@router.get("/{job_id}/logs/{name:path}")
def download_log(
    request: Request,
    job_id: str,
    name: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    job = get_owned_job(session, owner, job_id)
    entry = get_log(session, request.app.state.storage, job, name)
    path = log_path(request.app.state.storage, job, entry)
    return FileResponse(
        path,
        media_type=entry.content_type or "text/plain",
        filename=safe_download_name(entry.relative_path),
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{job_id}/spec")
def get_spec(
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> dict:
    """Return the canonical validated specification used to generate TOML."""

    import json

    job = get_owned_job(session, owner, job_id)
    try:
        return json.loads(job.spec_json)
    except ValueError as exc:  # pragma: no cover - defensive
        raise APIError(
            500, "invalid_stored_spec", "Stored job specification is corrupt"
        ) from exc


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel(
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobOut:
    job = cancel_job(session, owner, job_id)
    return JobOut.model_validate(job_to_dict(session, job))


@router.post("/{job_id}/retry", response_model=JobOut)
def retry(
    job_id: str,
    body: RetryRequest,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobOut:
    job = retry_job(session, owner, job_id, body)
    return JobOut.model_validate(job_to_dict(session, job))
