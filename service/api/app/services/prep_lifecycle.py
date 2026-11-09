"""Prep-job lifecycle transitions shared by the public API and prep worker.

Every state-changing function runs under the process-wide write lock.  Claim
uses ``BEGIN IMMEDIATE`` so the selection and update of a prep job are one
transaction.
"""

from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import immediate_transaction, write_transaction
from ..errors import APIError
from ..models import PrepJob
from ..schemas_internal import (
    PrepCancelRequest,
    PrepClaimRequest,
    PrepClaimResponse,
    PrepFinishRequest,
    PrepFinishResponse,
    PrepProgressRequest,
    PrepProgressResponse,
)
from ..settings import Settings
from ..storage import LocalStorage
from ..timeutils import iso_after, utcnow_iso

ACTIVE_STATUSES = ("claimed", "running")
TERMINAL_STATUSES = ("completed", "failed", "canceled")


def _token_matches(expected: str | None, provided: str) -> bool:
    import hmac
    return expected is not None and hmac.compare_digest(expected, provided)


def _lease_expiry(settings: Settings) -> str:
    return iso_after(settings.prep_heartbeat_seconds)


def _job_by_run_token(session: Session, prep_job_id: str, run_token: str) -> PrepJob:
    """Return a claimed/running prep job whose current run token matches."""

    job = session.get(PrepJob, prep_job_id)
    if job is None:
        raise APIError(404, "prep_job_not_found", f"Prep job {prep_job_id!r} not found")
    if not _token_matches(job.run_token, run_token):
        raise APIError(
            409,
            "stale_run_token",
            "The run token is no longer valid for this prep job",
        )
    if job.status not in ACTIVE_STATUSES:
        raise APIError(
            409,
            "invalid_state",
            f"Prep job in state {job.status!r} cannot be updated by a worker",
            {"status": job.status},
        )
    return job


def claim_prep(
    session: Session,
    settings: Settings,
    payload: PrepClaimRequest,
) -> PrepClaimResponse | None:
    """Atomically claim the oldest queued prep job.

    Returns ``None`` when the queue is empty.
    """

    with immediate_transaction(session):
        now = utcnow_iso()

        job = session.scalar(
            select(PrepJob)
            .where(PrepJob.status == "queued")
            .where(PrepJob.cancel_requested == False)  # noqa: E712
            .order_by(PrepJob.created_at.asc(), PrepJob.id.asc())
            .limit(1)
        )

        if job is None:
            return None

        run_token = str(uuid.uuid4())
        job.status = "claimed"
        job.run_token = run_token
        job.cancel_requested = False
        job.updated_at = now

        request = _load_json(job.request_json)
        job_type = request.get("type")
        # Backward-compat: detect job type from available fields for old jobs
        # that don't have an explicit "type" key in request_json.
        if job_type is None:
            if "steps" in request or "input_file_id" in request or "pdb_id" in request:
                job_type = "system_prep"
            else:
                job_type = "membrane_embed"

        response_kwargs: dict[str, Any] = {
            "prep_job_id": job.id,
            "run_token": run_token,
            "job_type": job_type,
            "source_path": "",  # filled in by the router
            "work_dir": "",     # filled in by the router
        }
        if job_type == "system_prep":
            response_kwargs["steps"] = request.get("steps", [])
        else:
            response_kwargs.update(
                {
                    "protein_file_id": request["protein_file_id"],
                    "lipid": request["lipid"],
                    "box_padding_nm": request["box_padding_nm"],
                    "orientation": request.get("orientation"),
                    "ionic_strength_molar": request["ionic_strength_molar"],
                }
            )

        response = PrepClaimResponse(**response_kwargs)

        session.commit()

    return response


def update_prep_progress(
    session: Session,
    settings: Settings,
    prep_job_id: str,
    payload: PrepProgressRequest,
) -> PrepProgressResponse:
    """Report progress for a claimed prep job."""

    with write_transaction(session):
        job = _job_by_run_token(session, prep_job_id, payload.run_token)
        now = utcnow_iso()

        job.status = "running"
        job.updated_at = now
        job.lease_expires_at = _lease_expiry(settings)

        if payload.phase is not None:
            job.phase = payload.phase
        if payload.percent is not None:
            job.progress_percent = payload.percent
        job.progress_updated_at = now

        cancel_requested = bool(job.cancel_requested)
        lease_expires_at = job.lease_expires_at

    return PrepProgressResponse(
        cancel_requested=cancel_requested,
        lease_expires_at=lease_expires_at,
    )


def finish_prep(
    session: Session,
    storage: LocalStorage,
    prep_job_id: str,
    payload: PrepFinishRequest,
) -> PrepFinishResponse:
    """Mark a prep job as completed or failed."""

    with write_transaction(session):
        job = _job_by_run_token(session, prep_job_id, payload.run_token)
        now = utcnow_iso()

        job.status = payload.status
        job.completed_at = now
        job.updated_at = now

        if payload.status == "failed":
            if payload.error_code:
                job.error_message = payload.error_message or payload.error_code
            else:
                job.error_code = "prep_worker_error"
                job.error_message = payload.error_message or "Prep worker failed"

        _clear_run(job)

        import json
        job.result_json = json.dumps(
            {
                "output_file_ids": payload.output_file_ids,
                "error_code": payload.error_code,
                "error_message": payload.error_message,
            },
            separators=(",", ":"),
        )

    return PrepFinishResponse(status=payload.status)


def cancel_prep(
    session: Session,
    prep_job_id: str,
) -> PrepJob | None:
    """Request cancellation of a queued or claimed prep job."""

    with immediate_transaction(session):
        now = utcnow_iso()
        job = session.get(PrepJob, prep_job_id)
        if job is None:
            raise APIError(404, "prep_job_not_found", f"Prep job {prep_job_id!r} not found")

        if job.status == "queued":
            job.status = "canceled"
            job.cancel_requested = True
            job.completed_at = now
            job.updated_at = now
            _clear_run(job)
            return job

        if job.status in ("claimed", "running"):
            job.status = "canceling"
            job.cancel_requested = True
            job.updated_at = now
            return job

        if job.status == "canceling":
            return job

        raise APIError(
            409,
            "invalid_state",
            f"Prep job in state {job.status!r} cannot be canceled",
            {"status": job.status},
        )


def _clear_run(job: PrepJob) -> None:
    job.run_token = None
    job.lease_expires_at = None


def _load_json(text: str | None) -> dict:
    import json
    if not text:
        return {}
    return json.loads(text)
