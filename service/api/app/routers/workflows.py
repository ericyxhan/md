"""Workflow API: base systems and derived simulation jobs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..errors import APIError
from ..models import FileRecord, Job, Workflow
from ..schemas import (
    JobCreate,
    JobListOut,
    JobOut,
    MinimizationSpec,
    ParameterizationSpec,
    ProductionSpec,
    StageSpec,
    WorkflowCreate,
    WorkflowDetailOut,
    WorkflowJobSummary,
    WorkflowOut,
    WorkflowVariantsRequest,
)
from ..security import require_owner
from ..services.jobs import (
    add_audit,
    add_event,
    build_canonical_spec,
    create_job,
    job_to_dict,
    list_jobs,
    stage_rows,
)
from ..services.queue import queue_positions
from ..settings import Settings
from ..storage import LocalStorage
from ..timeutils import utcnow_iso

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _owned_file(session: Session, owner_id: str, file_id: str) -> FileRecord:
    record = session.get(FileRecord, file_id)
    if record is None or record.owner_id != owner_id:
        raise APIError(404, "file_not_found", f"File {file_id!r} was not found")
    return record


def _workflow_job_counts(
    session: Session, workflow_ids: list[str]
) -> dict[str, int]:
    """Count the child jobs of every workflow with a single grouped query."""

    if not workflow_ids:
        return {}
    rows = session.execute(
        select(Job.workflow_id, func.count(Job.id))
        .where(Job.workflow_id.in_(workflow_ids))
        .group_by(Job.workflow_id)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def _workflow_out(
    session: Session, workflow: Workflow, job_count: int | None = None
) -> WorkflowOut:
    if job_count is None:
        job_count = _workflow_job_counts(session, [workflow.id]).get(workflow.id, 0)
    return WorkflowOut(
        id=workflow.id,
        name=workflow.name,
        source_file_id=workflow.source_file_id,
        source_type=workflow.source_type,
        job_count=job_count or 0,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _job_summary(job: Job) -> WorkflowJobSummary:
    return WorkflowJobSummary(
        id=job.id,
        name=job.name,
        status=job.status,
        phase=job.phase,
        progress={
            "step": job.progress_step,
            "total_steps": job.progress_total_steps,
            "percent": job.progress_percent,
            "updated_at": job.progress_updated_at,
        },
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow(
    request: Request,
    body: WorkflowCreate,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> WorkflowOut:
    """Register a completed prep/embed output file as a workflow base system."""

    _owned_file(session, owner, body.source_file_id)

    now = utcnow_iso()
    workflow = Workflow(
        id=str(uuid.uuid4()),
        owner_id=owner,
        name=body.name,
        source_file_id=body.source_file_id,
        source_type=body.source_type,
        created_at=now,
        updated_at=now,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return _workflow_out(session, workflow)


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> list[WorkflowOut]:
    """List all workflows for the owner, newest first."""

    statement = (
        select(Workflow)
        .where(Workflow.owner_id == owner)
        .order_by(Workflow.created_at.desc(), Workflow.id.desc())
    )
    workflows = list(session.scalars(statement).all())
    counts = _workflow_job_counts(session, [w.id for w in workflows])
    return [
        _workflow_out(session, w, counts.get(w.id, 0)) for w in workflows
    ]


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(
    workflow_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> WorkflowDetailOut:
    """Get a workflow with its child jobs."""

    workflow = session.get(Workflow, workflow_id)
    if workflow is None or workflow.owner_id != owner:
        raise APIError(404, "workflow_not_found", f"Workflow {workflow_id!r} was not found")

    statement = (
        select(Job)
        .where(Job.workflow_id == workflow_id)
        .order_by(Job.created_at.desc(), Job.id.desc())
    )
    jobs = list(session.scalars(statement).all())

    return WorkflowDetailOut(
        id=workflow.id,
        name=workflow.name,
        source_file_id=workflow.source_file_id,
        source_type=workflow.source_type,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        jobs=[_job_summary(j) for j in jobs],
    )


@router.post("/{workflow_id}/variants", response_model=JobListOut)
def create_workflow_variants(
    workflow_id: str,
    body: WorkflowVariantsRequest,
    request: Request,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> JobListOut:
    """Create N variant simulation jobs from a workflow's base system."""

    workflow = session.get(Workflow, workflow_id)
    if workflow is None or workflow.owner_id != owner:
        raise APIError(404, "workflow_not_found", f"Workflow {workflow_id!r} was not found")

    settings: Settings = request.app.state.settings
    storage: LocalStorage = request.app.state.storage

    created_at = utcnow_iso()
    base_name = workflow.name
    created_jobs: list[Job] = []

    for n in range(1, body.count + 1):
        name = body.name_template.replace("{name}", base_name).replace(
            "{n}", str(n)
        )

        job_create = JobCreate(
            name=name,
            input={
                "mode": "complex",
                "complex_file_id": workflow.source_file_id,
            },
            parameterization=body.parameterization
            or ParameterizationSpec(),
            minimization=body.minimization or MinimizationSpec(),
            equilibration=body.equilibration or [],
            production=body.production or ProductionSpec(enabled=False),
        )

        job = create_job(
            session,
            settings,
            storage,
            job_create,
            owner,
        )
        job.workflow_id = workflow.id
        session.add(job)

        add_event(
            session,
            job.id,
            "created",
            f"Job {job.name!r} created from workflow {workflow.name!r}",
            {"workflow_id": workflow.id, "variant": n},
        )
        add_event(session, job.id, "queued", "Job queued")
        add_audit(
            session,
            action="job.create",
            outcome="accepted",
            owner_id=owner,
            target_type="job",
            target_id=job.id,
            details={
                "input_mode": "complex",
                "workflow_id": workflow.id,
                "variant": n,
            },
        )
        created_jobs.append(job)

    session.commit()
    for job in created_jobs:
        session.refresh(job)

    positions = queue_positions(session, created_jobs)
    return JobListOut(
        items=[
            JobOut.model_validate(
                job_to_dict(session, job, queue_positions=positions)
            )
            for job in created_jobs
        ],
        next_cursor=None,
    )


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
):
    """Delete a workflow. Child jobs are left intact (workflow_id set NULL)."""

    workflow = session.get(Workflow, workflow_id)
    if workflow is None or workflow.owner_id != owner:
        raise APIError(404, "workflow_not_found", f"Workflow {workflow_id!r} was not found")

    for job in session.scalars(select(Job).where(Job.workflow_id == workflow_id)):
        job.workflow_id = None

    session.delete(workflow)
    session.commit()
    return None
