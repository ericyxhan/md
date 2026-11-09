"""System-preparation endpoints: membrane embedding."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request

from ..db import create_session_factory
from ..errors import APIError
from ..models import FileRecord, PrepJob
from ..schemas import (
    MembraneEmbedOut,
    MembraneEmbedRequest,
    PrepJobStatus,
    SystemPrepOut,
    SystemPrepRequest,
)
from ..security import require_owner
from ..services.prep import queue_membrane_embed, queue_system_prep
from ..services.prep_lifecycle import cancel_prep
from ..timeutils import utcnow_iso

router = APIRouter(tags=["prep"])


@router.post("/prep/membrane", response_model=MembraneEmbedOut)
def request_membrane_embed(
    request: Request,
    body: MembraneEmbedRequest,
    owner: str = Depends(require_owner),
) -> MembraneEmbedOut:
    """Queue a membrane embedding job.

    The uploaded protein file (PDB or mmCIF) is embedded into a lipid bilayer
    using Packmol-Memgen.  Returns immediately; poll
    ``GET /api/v1/prep/jobs/{prep_job_id}`` for completion.
    """

    settings = request.app.state.settings
    if not settings.packmol_path:
        raise APIError(
            503,
            "prep_not_configured",
            "System preparation is not configured on this server",
        )

    prep_job_id = str(uuid.uuid4())
    session_factory = create_session_factory(request.app.state.engine)

    with session_factory() as session:
        job = PrepJob(
            id=prep_job_id,
            owner_id=owner,
            type="membrane_embed",
            status="queued",
            request_json=json.dumps(
                {
                    "protein_file_id": body.protein_file_id,
                    "lipid": body.lipid,
                    "box_padding_nm": body.box_padding_nm,
                    "orientation": body.orientation,
                    "ionic_strength_molar": body.ionic_strength_molar,
                },
                separators=(",", ":"),
            ),
            created_at=utcnow_iso(),
            updated_at=utcnow_iso(),
        )
        session.add(job)
        session.commit()

    # Validate the input file before leaving the job queued for the worker.
    # This runs synchronously so invalid inputs are rejected immediately.
    try:
        queue_membrane_embed(
            prep_job_id=prep_job_id,
            owner=owner,
            protein_file_id=body.protein_file_id,
            lipid=body.lipid,
            box_padding_nm=body.box_padding_nm,
            orientation=body.orientation,
            ionic_strength_molar=body.ionic_strength_molar,
            settings=settings,
        )
    except APIError:
        # If validation fails, mark the job as failed and re-raise.
        with session_factory() as session:
            job = session.get(PrepJob, prep_job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = "Input validation failed"
                job.completed_at = utcnow_iso()
                job.updated_at = utcnow_iso()
                session.commit()
        raise

    return MembraneEmbedOut(
        prep_job_id=prep_job_id,
        status="queued",
    )


@router.post("/prep/system-prep", response_model=SystemPrepOut)
def request_system_prep(
    request: Request,
    body: SystemPrepRequest,
    owner: str = Depends(require_owner),
) -> SystemPrepOut:
    """Queue a system-preparation job (ligand removal, chain selection, ligand addition).

    Returns immediately; poll ``GET /api/v1/prep/jobs/{prep_job_id}`` for completion.
    Output files are registered as FileRecords and can be referenced as
    ``complex_file_id`` in MD job creation.
    """

    settings = request.app.state.settings
    prep_job_id = str(uuid.uuid4())
    session_factory = create_session_factory(request.app.state.engine)

    # Validate the input file exists and is owned (if not a PDB ID download).
    input_file_id: str | None = None
    if body.input_file_id:
        with session_factory() as session:
            file_record = session.get(FileRecord, body.input_file_id)
            if file_record is None or file_record.owner_id != owner:
                raise APIError(
                    404, "file_not_found", f"File {body.input_file_id!r} not found"
                )
            input_file_id = body.input_file_id

    with session_factory() as session:
        job = PrepJob(
            id=prep_job_id,
            owner_id=owner,
            type="system_prep",
            status="queued",
            request_json=json.dumps(
                {
                    "type": "system_prep",
                    "name": body.name,
                    "input_file_id": input_file_id,
                    "pdb_id": body.pdb_id,
                    "steps": [
                        {
                            "operation": step.operation,
                            "ligand_to_remove": step.ligand_to_remove,
                            "chain_to_keep": step.chain_to_keep,
                            "ligand_file_ids": step.ligand_file_ids,
                        }
                        for step in body.steps
                    ],
                },
                separators=(",", ":"),
            ),
            created_at=utcnow_iso(),
            updated_at=utcnow_iso(),
        )
        session.add(job)
        session.commit()

    try:
        queue_system_prep(
            prep_job_id=prep_job_id,
            owner=owner,
            input_file_id=input_file_id,
            pdb_id=body.pdb_id,
            steps=body.steps,
            settings=settings,
        )
    except APIError:
        with session_factory() as session:
            job = session.get(PrepJob, prep_job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = "Input validation failed"
                job.completed_at = utcnow_iso()
                job.updated_at = utcnow_iso()
                session.commit()
        raise

    return SystemPrepOut(
        prep_job_id=prep_job_id,
        status="queued",
    )


@router.get("/prep/jobs/{prep_job_id}", response_model=PrepJobStatus)
def get_prep_job_status(
    request: Request,
    prep_job_id: str,
    owner: str = Depends(require_owner),
) -> PrepJobStatus:
    """Return the status of a system-preparation job."""

    settings = request.app.state.settings
    session_factory = create_session_factory(request.app.state.engine)

    with session_factory() as session:
        job = session.get(PrepJob, prep_job_id)
        if job is None or job.owner_id != owner:
            raise APIError(
                404, "prep_job_not_found", f"Prep job {prep_job_id!r} not found"
            )

        output_file_ids = []
        if job.output_file_ids:
            output_file_ids = json.loads(job.output_file_ids)

        return PrepJobStatus(
            id=job.id,
            type=job.type,
            status=job.status,
            created_at=job.created_at,
            completed_at=job.completed_at,
            output_file_ids=output_file_ids,
            error=job.error_message,
        )


@router.get("/prep/jobs", response_model=list[PrepJobStatus])
def list_prep_jobs_endpoint(
    request: Request,
    owner: str = Depends(require_owner),
) -> list[PrepJobStatus]:
    """List the caller's system-preparation jobs."""

    settings = request.app.state.settings
    session_factory = create_session_factory(request.app.state.engine)

    from sqlalchemy import select

    with session_factory() as session:
        statement = (
            select(PrepJob)
            .where(PrepJob.owner_id == owner)
            .order_by(PrepJob.created_at.desc())
        )
        jobs = list(session.scalars(statement))

    result = []
    for job in jobs:
        output_file_ids = []
        if job.output_file_ids:
            output_file_ids = json.loads(job.output_file_ids)
        result.append(
            PrepJobStatus(
                id=job.id,
                type=job.type,
                status=job.status,
                created_at=job.created_at,
                completed_at=job.completed_at,
                output_file_ids=output_file_ids,
                error=job.error_message,
            )
        )
    return result


@router.post("/prep/jobs/{prep_job_id}/cancel", response_model=dict)
def cancel_prep_job(
    request: Request,
    prep_job_id: str,
    owner: str = Depends(require_owner),
) -> dict:
    """Request cancellation of a queued or running prep job."""

    settings = request.app.state.settings
    session_factory = create_session_factory(request.app.state.engine)

    with session_factory() as session:
        job = session.get(PrepJob, prep_job_id)
        if job is None or job.owner_id != owner:
            raise APIError(
                404, "prep_job_not_found", f"Prep job {prep_job_id!r} not found"
            )

        if job.status in ("completed", "failed", "canceled"):
            return {"status": job.status}

        job.cancel_requested = True
        job.updated_at = utcnow_iso()
        if job.status == "queued":
            job.status = "canceled"
            job.completed_at = utcnow_iso()
        elif job.status in ("claimed", "running"):
            job.status = "canceling"
        session.commit()

        return {"status": job.status}
