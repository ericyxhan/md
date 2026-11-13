"""Internal prep-worker protocol.

These routes are authenticated with ``X-Worker-Token`` instead of the public
bearer token and are hidden from the public OpenAPI document.  A dedicated prep
worker claims prep jobs, runs Packmol-Memgen, and reports progress/finish.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..db import create_session_factory, get_session
from ..errors import APIError
from ..models import FileRecord, PrepJob
from ..schemas_internal import (
    PrepCancelRequest,
    PrepCancelResponse,
    PrepClaimRequest,
    PrepClaimResponse,
    PrepFinishRequest,
    PrepFinishResponse,
    PrepProgressRequest,
    PrepProgressResponse,
)
from ..security import require_worker
from ..services import prep, prep_lifecycle
from ..services.prep_lifecycle import _load_json
from ..storage import LocalStorage

router = APIRouter(
    prefix="/internal/v1/prep",
    tags=["internal-prep"],
    include_in_schema=False,
    dependencies=[Depends(require_worker)],
)


@router.post("/claim", response_model=PrepClaimResponse)
def claim(
    request: Request,
    body: PrepClaimRequest,
    session: Session = Depends(get_session),
):
    """Claim the oldest queued prep job.  204 when the queue is empty."""

    settings = request.app.state.settings
    result = prep_lifecycle.claim_prep(
        session, settings, body
    )
    if result is None:
        return Response(status_code=204)

    # Re-fetch the PrepJob row so we can read request_json (the claim response
    # itself doesn't carry the raw request JSON).
    job = session.get(PrepJob, result.prep_job_id)
    if job is None:
        raise APIError(
            404, "prep_job_not_found", f"Prep job {result.prep_job_id} not found"
        )

    # Each account has its own preparation workspaces.
    storage = LocalStorage(settings)
    work_dir = storage.owner_prep(job.owner_id) / result.prep_job_id

    # Resolve the request data to determine job type and parameters.
    request_data = _load_json(job.request_json)
    job_type = request_data.get("type")
    # Backward-compat: detect job type from available fields
    if job_type is None:
        if "steps" in request_data or "input_file_id" in request_data or "pdb_id" in request_data:
            job_type = "system_prep"
        else:
            job_type = "membrane_embed"

    if job_type == "system_prep":
        # For system prep, resolve input and ligand file paths.
        input_file_id = request_data.get("input_file_id")
        source_path: str | None = None
        if input_file_id:
            file_record = session.get(FileRecord, input_file_id)
            if file_record is None:
                raise APIError(
                    404, "file_not_found", f"Source file {input_file_id} not found"
                )
                source_path = str(storage.absolute_key(file_record.storage_key))

        # Resolve ligand file paths so the worker can find them.
        steps = []
        for step in request_data.get("steps", []):
            step_copy = dict(step)
            if step.get("operation") == "add_ligand":
                ligand_paths = {}
                for lig_id in step.get("ligand_file_ids", []):
                    lig_record = session.get(FileRecord, lig_id)
                    if lig_record is None:
                        raise APIError(
                            404, "file_not_found", f"Ligand file {lig_id} not found"
                        )
                    lig_path = str(storage.absolute_key(lig_record.storage_key))
                    ligand_paths[lig_id] = lig_path
                step_copy["_ligand_paths"] = ligand_paths
            steps.append(step_copy)

        return PrepClaimResponse(
            prep_job_id=result.prep_job_id,
            run_token=result.run_token,
            owner_id=job.owner_id,
            job_type=job_type,
            steps=steps,
            source_path=source_path,
            work_dir=str(work_dir),
        )

    # membrane_embed (default)
    file_record = session.get(FileRecord, result.protein_file_id)
    if file_record is None:
        raise APIError(
            404, "file_not_found", f"Source file {result.protein_file_id} not found"
        )
    source_path = storage.absolute_key(file_record.storage_key)

    return PrepClaimResponse(
        prep_job_id=result.prep_job_id,
        run_token=result.run_token,
        owner_id=job.owner_id,
        job_type=job_type,
        protein_file_id=result.protein_file_id,
        lipid=result.lipid,
        box_padding_nm=result.box_padding_nm,
        orientation=result.orientation,
        ionic_strength_molar=result.ionic_strength_molar,
        source_path=str(source_path),
        work_dir=str(work_dir),
    )


@router.post("/{prep_job_id}/progress", response_model=PrepProgressResponse)
def progress(
    prep_job_id: str,
    request: Request,
    body: PrepProgressRequest,
    session: Session = Depends(get_session),
) -> PrepProgressResponse:
    """Report progress for a claimed prep job."""

    settings = request.app.state.settings
    return prep_lifecycle.update_prep_progress(
        session, settings, prep_job_id, body
    )


@router.post("/{prep_job_id}/finish", response_model=PrepFinishResponse)
def finish(
    prep_job_id: str,
    request: Request,
    body: PrepFinishRequest,
    session: Session = Depends(get_session),
) -> PrepFinishResponse:
    """Mark a prep job as completed or failed and register output files."""

    settings = request.app.state.settings
    storage = LocalStorage(settings)

    # Get the owner before finishing (the transaction will close the session)
    job_owner = ""
    with request.app.state.session_factory() as s2:
        job = s2.get(PrepJob, prep_job_id)
        if job is None:
            raise APIError(
                404, "prep_job_not_found", f"Prep job {prep_job_id!r} not found"
            )
        job_owner = job.owner_id

    # Convert path strings to Path objects
    output_paths = [Path(p) for p in body.output_file_ids] if body.output_file_ids else []

    prep.finish_prep_job(
        prep_job_id=prep_job_id,
        owner=job_owner,
        status=body.status,
        output_paths=output_paths,
        error_code=body.error_code,
        error_message=body.error_message,
        settings=settings,
        storage=storage,
    )

    return PrepFinishResponse(status=body.status)


@router.post("/heartbeat")
def prep_heartbeat(
    request: Request,
    body: dict,
) -> dict:
    """Prep worker heartbeat.

    Returns the cancel flag for the worker's current prep job, if any.
    Does not track leases (prep jobs are short-lived), but does surface
    cancellation requests so the worker can stop packmol-memgen.
    """

    cancel_requested = False
    current_job_id = body.get("current_job_id")
    if current_job_id:
        session_factory = request.app.state.session_factory
        with session_factory() as session:
            from ..models import PrepJob

            job = session.get(PrepJob, current_job_id)
            if job is not None and job.status in ("claimed", "running"):
                cancel_requested = bool(job.cancel_requested)

    return {"cancel_requested": cancel_requested}
