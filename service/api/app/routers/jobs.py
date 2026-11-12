"""Public job API."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..schemas import (
    ArtifactListOut,
    ArtifactOut,
    EventOut,
    EventWithJobOut,
    JobCreate,
    JobListOut,
    JobOut,
    JobPlanOut,
    JobValidateRequest,
    LogListOut,
    LogOut,
    LogTailOut,
    RetryRequest,
    SeriesOut,
    ViewFileOut,
    ViewListOut,
    ViewOut,
)
from ..security import require_owner
from ..services.artifacts import (
    artifact_path,
    build_job_views,
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
    list_events_across_jobs,
    list_jobs,
    validate_job,
)
from ..services.lifecycle import cancel_job, retry_job
from ..services.queue import queue_positions
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
    # One ranked query for the whole page instead of a COUNT per job.
    positions = queue_positions(session, jobs)
    return JobListOut(
        items=[
            JobOut.model_validate(
                job_to_dict(session, job, queue_positions=positions)
            )
            for job in jobs
        ],
        next_cursor=next_cursor,
    )


@router.get("/events", response_model=list[EventWithJobOut])
def list_events_all(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> list[EventWithJobOut]:
    """Recent events across all jobs owned by the caller.

    Returns events joined with their parent job, newest first, so a user
    can scan a single notification history and click through to any job.
    """
    events, _next_cursor = list_events_across_jobs(
        session, owner, limit=limit, cursor=cursor
    )
    return [EventWithJobOut.model_validate(event) for event in events]


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


@router.get("/{job_id}/views", response_model=ViewListOut)
def get_views(
    request: Request,
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> ViewListOut:
    """Browser-oriented inventory of derived structure/trajectory views.

    Views are small, solute-focused derivatives written by the worker under
    ``outputs/views/``; this endpoint groups them by view (``prepared`` or a
    stage name) and inlines the JSON manifest so the client can caption the
    structure without extra requests. File contents are fetched through the
    regular artifact download route referenced by ``url``.
    """

    job = get_owned_job(session, owner, job_id)
    base = f"/api/v1/jobs/{job.id}/artifacts"

    def file_out(artifact) -> ViewFileOut:
        return ViewFileOut(
            id=artifact.id,
            name=safe_download_name(artifact.relative_path),
            relative_path=artifact.relative_path,
            size_bytes=artifact.size_bytes,
            url=f"{base}/{artifact.id}",
        )

    items: list[ViewOut] = []
    for summary in build_job_views(session, request.app.state.storage, job):
        files = summary.files
        items.append(
            ViewOut(
                group=files.group,
                structure=(
                    file_out(files.structure) if files.structure else None
                ),
                trajectory=(
                    file_out(files.trajectory) if files.trajectory else None
                ),
                manifest=file_out(files.manifest) if files.manifest else None,
                manifest_data=summary.manifest_data,
            )
        )
    return ViewListOut(items=items)


@router.get("/{job_id}/analysis/series", response_model=SeriesOut)
def get_job_series(
    request: Request,
    job_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> SeriesOut:
    """Downsampled time series from a stage's simulation.log.

    Returns the worker-generated ``outputs/analysis/series.json`` for the
    most recent completed stage that has a state log.  Points are
    server-downsampled to at most 2,000 with minima and maxima preserved.
    """

    job = get_owned_job(session, owner, job_id)
    storage = request.app.state.storage

    artifacts = list_artifacts(session, job, kind="analysis")
    series_artifacts = [
        item
        for item in artifacts
        if item.relative_path.endswith("outputs/analysis/series.json")
    ]
    if not series_artifacts:
        raise APIError(
            404,
            "series_not_found",
            "No analysis series is available for this job.",
        )

    # Prefer the latest completed stage's series (artifacts are sorted by
    # stage name; series.json is shared across stages, so take the first).
    artifact = series_artifacts[0]
    path = artifact_path(storage, job, artifact)
    if not path.is_file():
        raise APIError(
            404,
            "series_not_found",
            "Analysis series file is unavailable.",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise APIError(
            500,
            "series_read_failed",
            f"Could not read analysis series: {exc}",
        ) from exc

    # Map raw simulation.log column names to SeriesPoint schema fields.
    _COLUMN_MAP = {
        "Step": "step",
        "Time (ps)": "time_ps",
        "Potential Energy (kJ/mole)": "potential_energy_kj_mol",
        "Kinetic Energy (kJ/mole)": "kinetic_energy_kj_mol",
        "Temperature (K)": "temperature_k",
        "Density (g/mL)": "density_g_ml",
        "Box Volume (nm^3)": "volume_nm3",
        "Speed (ns/day)": "speed_ns_day",
        "Elapsed Time (s)": "elapsed_s",
    }

    raw_columns = data.get("columns", [])
    raw_points = data.get("points", [])
    columns = [_COLUMN_MAP.get(c, c) for c in raw_columns]
    points = []
    for raw_point in raw_points:
        point = {}
        for col, value in raw_point.items():
            point[_COLUMN_MAP.get(col, col)] = value
        points.append(point)

    return SeriesOut(
        group=data.get("group", ""),
        source=data.get("source", ""),
        source_points=data.get("source_points", 0),
        view_points=data.get("view_points", 0),
        columns=columns,
        points=points,
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


def _artifact_response(
    request: Request,
    job_id: str,
    artifact_id: str,
    owner: str,
    session: Session,
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


@router.get("/{job_id}/artifacts/{artifact_id}")
def download_artifact(
    request: Request,
    job_id: str,
    artifact_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    return _artifact_response(request, job_id, artifact_id, owner, session)


@router.head("/{job_id}/artifacts/{artifact_id}", include_in_schema=False)
def download_artifact_head(
    request: Request,
    job_id: str,
    artifact_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    """Return the artifact headers without the body.

    The viewer asks for the headers before it loads a structure, so a
    missing artifact shows as an error instead of an empty scene.
    """

    return _artifact_response(request, job_id, artifact_id, owner, session)


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
