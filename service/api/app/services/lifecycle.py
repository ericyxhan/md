"""Queue lifecycle transitions shared by the public and worker APIs.

Every function that changes state runs under the process-wide write lock.  The
claim, cancel, and retry functions additionally use ``BEGIN IMMEDIATE`` so the
selection and update of a job are one transaction.
"""

from __future__ import annotations

import hmac
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import immediate_transaction, write_transaction
from ..errors import APIError
from ..models import Job, JobStage, Worker
from ..schemas import RetryRequest
from ..schemas_internal import (
    ArtifactInput,
    ClaimRequest,
    ClaimResponse,
    ClaimStage,
    FinishRequest,
    ProgressRequest,
    ProgressResponse,
    StageUpdateRequest,
    StageUpdateResponse,
    WorkerHeartbeatRequest,
    WorkerHeartbeatResponse,
)
from ..settings import Settings
from ..storage import LocalStorage
from ..timeutils import iso_after, parse_iso, to_iso, utcnow_iso
from .artifacts import register_artifacts
from .audit import add_audit
from .events import add_event

ACTIVE_STATUSES = ("claimed", "running", "canceling")
TERMINAL_STATUSES = ("completed", "failed", "canceled")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lease_expiry(settings: Settings) -> str:
    return iso_after(settings.worker_lease_seconds)


def _token_matches(expected: str | None, provided: str) -> bool:
    return expected is not None and hmac.compare_digest(expected, provided)


def _job_by_run_token(session: Session, job_id: str, run_token: str) -> Job:
    """Return an active job whose current run token matches."""

    job = session.get(Job, job_id)
    if job is None:
        raise APIError(404, "job_not_found", f"Job {job_id!r} was not found")
    if not _token_matches(job.run_token, run_token):
        raise APIError(
            409,
            "stale_run_token",
            "The run token is no longer valid for this job",
        )
    if job.status not in ACTIVE_STATUSES:
        raise APIError(
            409,
            "invalid_state",
            f"Job in state {job.status!r} cannot be updated by a worker",
            {"status": job.status},
        )
    return job


def _upsert_worker(
    session: Session,
    *,
    worker_id: str,
    hostname: str,
    status: str,
    gpu_name: str | None = None,
    gpu_uuid: str | None = None,
    version: str | None = None,
    current_job_id: str | None = None,
    now: str,
) -> Worker:
    worker = session.get(Worker, worker_id)
    if worker is None:
        worker = Worker(
            id=worker_id,
            hostname=hostname,
            gpu_name=gpu_name,
            gpu_uuid=gpu_uuid,
            version=version,
            status=status,
            current_job_id=current_job_id,
            last_heartbeat_at=now,
            registered_at=now,
        )
        session.add(worker)
    else:
        worker.hostname = hostname
        if gpu_name is not None:
            worker.gpu_name = gpu_name
        if gpu_uuid is not None:
            worker.gpu_uuid = gpu_uuid
        if version is not None:
            worker.version = version
        worker.status = status
        worker.current_job_id = current_job_id
        worker.last_heartbeat_at = now
    return worker


def _mark_running(session: Session, job: Job, now: str) -> None:
    if job.status == "claimed":
        job.status = "running"
        if job.started_at is None:
            job.started_at = now
        add_event(
            session,
            job.id,
            "running",
            f"Job {job.name!r} started running",
            {"worker_id": job.worker_id, "attempt": job.attempt},
        )


def _clear_run(job: Job) -> None:
    job.worker_id = None
    job.run_token = None
    job.lease_expires_at = None


# ---------------------------------------------------------------------------
# Worker heartbeat and claim
# ---------------------------------------------------------------------------


def heartbeat(
    session: Session,
    settings: Settings,
    payload: WorkerHeartbeatRequest,
) -> WorkerHeartbeatResponse:
    """Register a worker and extend the lease for a matching active job."""

    with write_transaction(session):
        now = utcnow_iso()
        cancel_requested = False
        lease_expires_at: str | None = None

        job: Job | None = None
        if payload.current_job_id and payload.run_token:
            job = session.get(Job, payload.current_job_id)

        matched = (
            job is not None
            and job.worker_id == payload.worker_id
            and _token_matches(job.run_token, payload.run_token or "")
            and job.status in ACTIVE_STATUSES
        )

        if matched and payload.status == "online":
            assert job is not None
            job.lease_expires_at = _lease_expiry(settings)
            job.updated_at = now
            cancel_requested = bool(job.cancel_requested)
            lease_expires_at = job.lease_expires_at

        _upsert_worker(
            session,
            worker_id=payload.worker_id,
            hostname=payload.hostname,
            status=payload.status,
            gpu_name=payload.gpu_name,
            gpu_uuid=payload.gpu_uuid,
            version=payload.version,
            current_job_id=payload.current_job_id
            if payload.status == "online"
            else None,
            now=now,
        )

    return WorkerHeartbeatResponse(
        cancel_requested=cancel_requested,
        lease_expires_at=lease_expires_at,
    )


def claim(
    session: Session,
    settings: Settings,
    storage: LocalStorage,
    payload: ClaimRequest,
) -> ClaimResponse | None:
    """Atomically claim the oldest queued job.

    Returns ``None`` when the queue is empty.  The route turns that into a
    ``204 No Content`` response.
    """

    with immediate_transaction(session):
        now = utcnow_iso()

        job = session.scalar(
            select(Job)
            .where(Job.status == "queued")
            .order_by(Job.queued_at.asc(), Job.created_at.asc(), Job.id.asc())
            .limit(1)
        )

        _upsert_worker(
            session,
            worker_id=payload.worker_id,
            hostname=payload.worker_id,
            status="online",
            gpu_uuid=payload.gpu_uuid,
            current_job_id=job.id if job is not None else None,
            now=now,
        )

        if job is None:
            return None

        job.status = "claimed"
        job.worker_id = payload.worker_id
        job.run_token = str(uuid.uuid4())
        job.lease_expires_at = _lease_expiry(settings)
        job.attempt += 1
        job.queued_at = job.queued_at or now
        job.started_at = job.started_at or now
        job.updated_at = now
        job.cancel_requested = False
        job.phase = None
        job.current_stage = None
        job.progress_step = None
        job.progress_total_steps = None
        job.progress_percent = None
        job.progress_updated_at = None
        job.error_code = None
        job.error_message = None
        job.exit_code = None

        add_event(
            session,
            job.id,
            "claimed",
            f"Job claimed by worker {payload.worker_id!r}",
            {"worker_id": payload.worker_id, "attempt": job.attempt},
        )
        add_audit(
            session,
            action="job.claim",
            outcome="claimed",
            owner_id=job.owner_id,
            target_type="job",
            target_id=job.id,
            details={
                "worker_id": payload.worker_id,
                "attempt": job.attempt,
            },
        )

        stages = [
            ClaimStage(
                name=stage.name,
                kind=stage.kind,
                status=stage.status,
                steps_completed=stage.steps_completed,
                steps_target=stage.steps_target,
            )
            for stage in job.stages
        ]
        job_root = storage.job_root(job.id)
        response = ClaimResponse(
            job_id=job.id,
            run_token=job.run_token,
            config_path=str(job_root / "config.toml"),
            job_root=str(job_root),
            restart_mode=job.restart_mode or "resume",
            restart_stage=job.restart_stage,
            stages=stages,
        )

    return response


# ---------------------------------------------------------------------------
# Progress and stage updates
# ---------------------------------------------------------------------------


def update_progress(
    session: Session,
    settings: Settings,
    job_id: str,
    payload: ProgressRequest,
) -> ProgressResponse:
    with write_transaction(session):
        job = _job_by_run_token(session, job_id, payload.run_token)
        now = utcnow_iso()

        _mark_running(session, job, now)

        if payload.phase is not None and payload.phase != job.phase:
            previous = job.phase
            job.phase = payload.phase
            add_event(
                session,
                job.id,
                "phase_changed",
                f"Phase changed from {previous!r} to {payload.phase!r}",
                {"from": previous, "to": payload.phase},
            )

        if payload.stage is not None:
            job.current_stage = payload.stage

        if payload.step is not None:
            job.progress_step = payload.step
        if payload.total_steps is not None:
            job.progress_total_steps = payload.total_steps

        if payload.percent is not None:
            job.progress_percent = payload.percent
        elif payload.step is not None and payload.total_steps:
            job.progress_percent = min(
                100.0, max(0.0, 100.0 * payload.step / payload.total_steps)
            )

        if payload.updated_at:
            try:
                job.progress_updated_at = to_iso(parse_iso(payload.updated_at))
            except ValueError:
                job.progress_updated_at = now
        else:
            job.progress_updated_at = now

        job.lease_expires_at = _lease_expiry(settings)
        job.updated_at = now
        cancel_requested = bool(job.cancel_requested)
        lease_expires_at = job.lease_expires_at

    return ProgressResponse(
        cancel_requested=cancel_requested,
        lease_expires_at=lease_expires_at,
    )


def update_stage(
    session: Session,
    settings: Settings,
    job_id: str,
    payload: StageUpdateRequest,
) -> StageUpdateResponse:
    with write_transaction(session):
        job = _job_by_run_token(session, job_id, payload.run_token)
        now = utcnow_iso()

        stage = session.scalar(
            select(JobStage).where(
                JobStage.job_id == job.id,
                JobStage.name == payload.name,
            )
        )
        if stage is None:
            raise APIError(
                404,
                "stage_not_found",
                f"Stage {payload.name!r} does not belong to this job",
                {"available": [item.name for item in job.stages]},
            )

        manifest_json = None
        manifest_payload = payload.manifest
        if payload.manifest_json is not None:
            if isinstance(payload.manifest_json, str):
                if len(payload.manifest_json) > 1_000_000:
                    raise APIError(
                        413,
                        "manifest_too_large",
                        "Stage manifest exceeds the 1 MiB limit",
                    )
                try:
                    decoded = json.loads(payload.manifest_json)
                except ValueError as exc:
                    raise APIError(
                        422,
                        "invalid_manifest",
                        "manifest_json is not valid JSON",
                    ) from exc
            else:
                decoded = payload.manifest_json
            if not isinstance(decoded, dict):
                raise APIError(
                    422,
                    "invalid_manifest",
                    "manifest_json must be a JSON object",
                )
            manifest_payload = decoded
        if manifest_payload is not None:
            manifest_json = json.dumps(manifest_payload, sort_keys=True)
            if len(manifest_json) > 1_000_000:
                raise APIError(
                    413,
                    "manifest_too_large",
                    "Stage manifest exceeds the 1 MiB limit",
                )

        previous_status = stage.status
        _mark_running(session, job, now)
        stage.status = payload.status
        stage.steps_completed = payload.steps_completed
        stage.attempts = max(stage.attempts, payload.attempts)
        stage.error = payload.error
        stage.updated_at = now
        if manifest_json is not None:
            stage.manifest_json = manifest_json

        if payload.status == "running":
            if stage.started_at is None:
                stage.started_at = now
            stage.completed_at = None
            job.current_stage = stage.name
        elif payload.status in ("completed", "failed", "canceled", "skipped"):
            if stage.started_at is None:
                stage.started_at = now
            stage.completed_at = now
            if job.current_stage is None:
                job.current_stage = stage.name
        elif payload.status == "pending":
            stage.started_at = None
            stage.completed_at = None
            if manifest_json is None:
                stage.manifest_json = None

        if previous_status != payload.status:
            add_event(
                session,
                job.id,
                "stage",
                f"Stage {stage.name!r}: {previous_status} -> {payload.status}",
                {
                    "stage": stage.name,
                    "from": previous_status,
                    "to": payload.status,
                    "steps_completed": stage.steps_completed,
                },
            )

        job.lease_expires_at = _lease_expiry(settings)
        job.updated_at = now
        cancel_requested = bool(job.cancel_requested)

    return StageUpdateResponse(
        ok=True,
        cancel_requested=cancel_requested,
    )


# ---------------------------------------------------------------------------
# Finish
# ---------------------------------------------------------------------------


def finish(
    session: Session,
    storage: LocalStorage,
    job_id: str,
    payload: FinishRequest,
) -> dict[str, str]:
    with write_transaction(session):
        job = _job_by_run_token(session, job_id, payload.run_token)
        now = utcnow_iso()

        artifacts: list[ArtifactInput] = payload.artifacts
        register_artifacts(session, storage, job, artifacts)

        job.status = payload.status
        job.exit_code = payload.exit_code
        job.error_code = payload.error_code
        job.error_message = payload.error_message
        if payload.status == "failed":
            if job.error_code is None:
                job.error_code = "worker_error"
            if job.error_message is None:
                job.error_message = "The worker reported a failed job"
        job.completed_at = now
        job.updated_at = now

        running_worker = job.worker_id
        _clear_run(job)

        if running_worker is not None:
            worker = session.get(Worker, running_worker)
            if worker is not None:
                worker.status = "online"
                worker.current_job_id = None
                worker.last_heartbeat_at = now

        add_audit(
            session,
            action="job.finish",
            outcome=payload.status,
            owner_id=job.owner_id,
            target_type="job",
            target_id=job.id,
            details={
                "worker_id": running_worker,
                "exit_code": payload.exit_code,
                "error_code": job.error_code,
            },
        )

        if payload.status == "completed":
            add_event(session, job.id, "completed", "Job completed")
        elif payload.status == "canceled":
            add_event(session, job.id, "canceled", "Job canceled")
        else:
            add_event(
                session,
                job.id,
                "failed",
                f"Job failed: {job.error_message}",
                {
                    "error_code": job.error_code,
                    "exit_code": job.exit_code,
                },
            )

        status = job.status

    return {"status": status}


# ---------------------------------------------------------------------------
# Public cancel and retry
# ---------------------------------------------------------------------------


def _owned_job(session: Session, owner_id: str, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.owner_id != owner_id:
        raise APIError(404, "job_not_found", f"Job {job_id!r} was not found")
    return job


def cancel_job(
    session: Session,
    owner_id: str,
    job_id: str,
) -> Job:
    with immediate_transaction(session):
        job = _owned_job(session, owner_id, job_id)
        now = utcnow_iso()

        if job.status == "queued":
            job.status = "canceled"
            job.cancel_requested = True
            job.completed_at = now
            job.updated_at = now
            _clear_run(job)
            add_event(
                session,
                job.id,
                "canceled",
                "Job canceled before it was claimed",
            )
            add_audit(
                session,
                action="job.cancel",
                outcome="canceled",
                owner_id=owner_id,
                target_type="job",
                target_id=job.id,
                details={"previous_status": "queued"},
            )
            return job

        if job.status in ("claimed", "running"):
            previous_status = job.status
            job.status = "canceling"
            job.cancel_requested = True
            job.updated_at = now
            add_event(
                session,
                job.id,
                "cancel_requested",
                "Cancellation requested",
                {"worker_id": job.worker_id},
            )
            add_audit(
                session,
                action="job.cancel",
                outcome="requested",
                owner_id=owner_id,
                target_type="job",
                target_id=job.id,
                details={
                    "previous_status": previous_status,
                    "worker_id": job.worker_id,
                },
            )
            return job

        if job.status == "canceling":
            return job

        raise APIError(
            409,
            "invalid_state",
            f"Job in state {job.status!r} cannot be canceled",
            {"status": job.status},
        )


def _reset_stages(
    job: Job,
    mode: str,
    target_index: int | None,
    now: str,
) -> None:
    stages = sorted(job.stages, key=lambda stage: stage.position)
    for index, stage in enumerate(stages):
        if mode == "resume":
            if stage.status in ("completed", "skipped"):
                continue
        elif mode == "restart_stage":
            if target_index is not None and index < target_index:
                continue

        stage.status = "pending"
        stage.steps_completed = 0
        stage.started_at = None
        stage.completed_at = None
        stage.error = None
        stage.manifest_json = None
        stage.updated_at = now


def retry_job(
    session: Session,
    owner_id: str,
    job_id: str,
    request: RetryRequest,
) -> Job:
    with immediate_transaction(session):
        job = _owned_job(session, owner_id, job_id)
        now = utcnow_iso()

        if job.status not in TERMINAL_STATUSES:
            raise APIError(
                409,
                "invalid_state",
                f"Job in state {job.status!r} cannot be retried",
                {"status": job.status},
            )
        if request.mode == "resume" and job.status == "completed":
            raise APIError(
                409,
                "invalid_retry_mode",
                "A completed job cannot be resumed; use restart or "
                "restart_stage",
            )

        stages = sorted(job.stages, key=lambda stage: stage.position)
        stage_names = [stage.name for stage in stages]
        target_index: int | None = None
        if request.mode == "restart_stage":
            if request.stage not in stage_names:
                raise APIError(
                    422,
                    "invalid_stage",
                    f"Stage {request.stage!r} does not belong to this job",
                    {"available": stage_names},
                )
            target_index = stage_names.index(request.stage or "")

        _reset_stages(job, request.mode, target_index, now)

        job.status = "queued"
        job.queued_at = now
        job.updated_at = now
        job.restart_mode = request.mode
        job.restart_stage = (
            request.stage if request.mode == "restart_stage" else None
        )
        job.cancel_requested = False
        _clear_run(job)
        job.phase = None
        job.current_stage = None
        job.progress_step = None
        job.progress_total_steps = None
        job.progress_percent = None
        job.progress_updated_at = None
        job.error_code = None
        job.error_message = None
        job.exit_code = None
        job.started_at = None
        job.completed_at = None

        add_event(
            session,
            job.id,
            "retried",
            f"Job queued for retry in {request.mode!r} mode",
            {"mode": request.mode, "stage": request.stage},
        )
        add_audit(
            session,
            action="job.retry",
            outcome="queued",
            owner_id=owner_id,
            target_type="job",
            target_id=job.id,
            details={"mode": request.mode, "stage": request.stage},
        )
        return job
