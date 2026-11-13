"""Job creation, materialization, listing, and serialization."""

from __future__ import annotations

import base64
import json
import re
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config_builder import build_config_toml
from ..errors import APIError
from ..models import FileRecord, Job, JobStage
from ..policies import build_canonical_spec, stage_rows
from ..schemas import JobCreate
from ..settings import Settings
from ..simulation_config import load_workflow_config
from ..storage import LocalStorage, StorageError, display_name, file_suffix
from ..timeutils import utcnow_iso
from .audit import add_audit
from .events import add_event
from .maintenance import check_queue_limit, ensure_disk_capacity
from .prep import prep_job_label
from .queue import queue_position, queue_positions

_PDB_ID_RE = re.compile(r"^[0-9A-Za-z]{4}$")
_RCSB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
_JOB_STATUSES = ("queued", "claimed", "running", "canceling", "completed", "failed", "canceled")


# ---------------------------------------------------------------------------
# File lookup and materialization
# ---------------------------------------------------------------------------


def _owned_file(session: Session, owner_id: str, file_id: str) -> FileRecord:
    record = session.get(FileRecord, file_id)
    if record is None or record.owner_id != owner_id:
        raise APIError(404, "file_not_found", f"File {file_id!r} was not found")
    return record


def _safe_suffix(original_name: str) -> str:
    try:
        return file_suffix(original_name)
    except StorageError as exc:
        raise APIError(400, "unsupported_file_type", str(exc)) from exc


def _relative_inputs(
    session: Session,
    owner_id: str,
    request: JobCreate,
    settings: Settings,
) -> dict[str, Any]:
    """Resolve uploaded files into relative input paths without copying."""

    spec = request.input
    if spec.mode == "pdb_id":
        assert spec.pdb_id is not None
        return {
            "mode": "pdb_id",
            "pdb_id": spec.pdb_id.upper(),
            "complex": "inputs/complex.pdb",
            "display_name": f"{spec.pdb_id.upper()}.pdb",
        }

    if spec.mode == "complex":
        assert spec.complex_file_id is not None
        record = _owned_file(session, owner_id, spec.complex_file_id)
        suffix = _safe_suffix(record.original_name)
        return {
            "mode": "complex",
            "complex": f"inputs/complex{suffix}",
            "display_name": display_name(record.original_name),
            "files": [record.id],
        }

    assert spec.protein_file_id is not None
    protein = _owned_file(session, owner_id, spec.protein_file_id)
    protein_suffix = _safe_suffix(protein.original_name)
    ligands: list[dict[str, Any]] = []
    for file_id in spec.ligand_file_ids:
        record = _owned_file(session, owner_id, file_id)
        suffix = _safe_suffix(record.original_name)
        ligands.append({"file_id": record.id, "suffix": suffix})
    return {
        "mode": "protein_ligands",
        "protein": f"inputs/protein{protein_suffix}",
        "ligands": [
            f"inputs/ligand-{index:02d}{ligand['suffix']}"
            for index, ligand in enumerate(ligands, 1)
        ],
        "display_name": "protein + ligands",
        "files": [protein.id, *(ligand["file_id"] for ligand in ligands)],
    }


def _check_upload_total(
    session: Session, inputs: dict[str, Any], settings: Settings
) -> int:
    total = 0
    for file_id in inputs.get("files", []):
        record = session.get(FileRecord, file_id)
        if record is not None:
            total += record.size_bytes
    if total > settings.max_job_upload_bytes:
        raise APIError(
            413,
            "job_upload_too_large",
            "Combined input files exceed the per-job upload limit",
            {"limit": settings.max_job_upload_bytes, "size_bytes": total},
        )
    return total


def _download_pdb(
    pdb_id: str, destination: Path, settings: Settings
) -> int:
    if not settings.allow_pdb_download:
        raise APIError(
            403,
            "pdb_download_disabled",
            "PDB downloads are disabled on this server",
        )
    if not _PDB_ID_RE.match(pdb_id):
        raise APIError(422, "invalid_pdb_id", "PDB ID must be four characters")

    url = _RCSB_URL.format(pdb_id=pdb_id.upper())
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    written = 0
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=settings.pdb_download_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "md-service/0.1"},
        ) as response:
            response.raise_for_status()
            declared = response.headers.get("content-length")
            if declared is not None and int(declared) > settings.max_upload_bytes:
                raise APIError(
                    413,
                    "pdb_download_too_large",
                    "Downloaded PDB exceeds the upload limit",
                )
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    written += len(chunk)
                    if written > settings.max_upload_bytes:
                        raise APIError(
                            413,
                            "pdb_download_too_large",
                            "Downloaded PDB exceeds the upload limit",
                        )
                    handle.write(chunk)
    except APIError:
        temporary.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise APIError(
            502,
            "pdb_download_failed",
            f"Could not download PDB {pdb_id.upper()}: {exc}",
        ) from exc

    if written == 0:
        temporary.unlink(missing_ok=True)
        raise APIError(502, "pdb_download_failed", "Downloaded PDB was empty")
    temporary.replace(destination)
    return written


def _materialize_inputs(
    session: Session,
    storage: LocalStorage,
    settings: Settings,
    owner_id: str,
    request: JobCreate,
    job_root: Path,
) -> dict[str, Any]:
    inputs = _relative_inputs(session, owner_id, request, settings)
    (job_root / "inputs").mkdir(parents=True, exist_ok=True)

    if inputs["mode"] == "pdb_id":
        _download_pdb(
            inputs["pdb_id"], job_root / inputs["complex"], settings
        )
        return inputs

    _check_upload_total(session, inputs, settings)
    for file_id in inputs.get("files", []):
        record = session.get(FileRecord, file_id)
        assert record is not None
        source = storage.absolute_key(record.storage_key)
        if not source.is_file():
            raise APIError(
                500,
                "input_file_missing",
                f"Stored input {record.id} is missing",
            )

    if inputs["mode"] == "complex":
        record = _owned_file(session, owner_id, request.input.complex_file_id or "")
        storage.copy_file(
            storage.absolute_key(record.storage_key), job_root / inputs["complex"]
        )
        return inputs

    protein = _owned_file(
        session, owner_id, request.input.protein_file_id or ""
    )
    storage.copy_file(
        storage.absolute_key(protein.storage_key), job_root / inputs["protein"]
    )
    for ligand_path, file_id in zip(inputs["ligands"], request.input.ligand_file_ids):
        record = _owned_file(session, owner_id, file_id)
        storage.copy_file(
            storage.absolute_key(record.storage_key), job_root / ligand_path
        )
    return inputs


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------


def _job_json(canonical: dict[str, Any], job_id: str, created_at: str) -> str:
    payload = {
        "job_id": job_id,
        "created_at": created_at,
        "spec": canonical,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def create_job(
    session: Session,
    settings: Settings,
    storage: LocalStorage,
    request: JobCreate,
    owner_id: str,
) -> Job:
    """Create a workspace, validate generated TOML, and queue the job."""

    storage.ensure_layout()
    check_queue_limit(session, owner_id, settings)
    ensure_disk_capacity(settings, storage)
    job_id = str(uuid.uuid4())
    final_root = storage.job_root(owner_id, job_id)
    temporary_root = storage.job_temp_root(owner_id, job_id)
    created_at = utcnow_iso()

    try:
        temporary_root.mkdir(parents=True, exist_ok=False)
        (temporary_root / "logs").mkdir(parents=True, exist_ok=True)

        inputs = _materialize_inputs(
            session, storage, settings, owner_id, request, temporary_root
        )
        canonical = build_canonical_spec(request, inputs, settings)

        # Generate with the final job root so paths stay correct after the
        # atomic rename.  Validate the file from its temporary location; the
        # simulation config loader resolves paths but does not require them to
        # exist yet.
        config_text = build_config_toml(canonical, final_root, settings)
        config_path = temporary_root / "config.toml"
        config_path.write_text(config_text, encoding="utf-8")
        load_workflow_config(config_path)

        (temporary_root / "job.json").write_text(
            _job_json(canonical, job_id, created_at), encoding="utf-8"
        )
        temporary_root.rename(final_root)
    except BaseException:
        storage.remove_tree(temporary_root)
        raise

    job = Job(
        id=job_id,
        owner_id=owner_id,
        name=request.name,
        status="queued",
        phase=None,
        spec_json=json.dumps(canonical, sort_keys=True, separators=(",", ":")),
        config_toml=config_text,
        input_mode=request.input.mode,
        restart_mode=None,
        restart_stage=None,
        attempt=0,
        worker_id=None,
        run_token=None,
        lease_expires_at=None,
        cancel_requested=False,
        current_stage=None,
        progress_step=None,
        progress_total_steps=None,
        progress_percent=None,
        progress_updated_at=None,
        error_code=None,
        error_message=None,
        exit_code=None,
        created_at=created_at,
        updated_at=created_at,
        queued_at=created_at,
        started_at=None,
        completed_at=None,
    )

    try:
        session.add(job)
        session.flush()
        stage_values = stage_rows(canonical)
        for row in stage_values:
            session.add(
                JobStage(
                    id=str(uuid.uuid4()),
                    job_id=job.id,
                    name=row["name"],
                    position=row["position"],
                    kind=row["kind"],
                    status="pending",
                    steps_target=row["steps_target"],
                    steps_completed=0,
                    attempts=0,
                    started_at=None,
                    completed_at=None,
                    updated_at=created_at,
                    error=None,
                    manifest_json=None,
                )
            )
        stage_names = [row["name"] for row in stage_values]
        add_event(
            session,
            job.id,
            "created",
            f"Job {job.name!r} created",
            {"stage_names": stage_names},
        )
        add_event(session, job.id, "queued", "Job queued")
        add_audit(
            session,
            action="job.create",
            outcome="accepted",
            owner_id=owner_id,
            target_type="job",
            target_id=job.id,
            details={
                "input_mode": request.input.mode,
                "stage_names": stage_names,
            },
        )
        session.commit()
    except BaseException:
        session.rollback()
        storage.remove_tree(final_root)
        raise

    session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Serialization and listings
# ---------------------------------------------------------------------------


def job_to_dict(
    session: Session,
    job: Job,
    *,
    queue_positions: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Serialize one job.

    ``queue_positions`` is the batched queue ranking produced by
    :func:`~app.services.queue.queue_positions`.  Pass it when serializing a
    list so the queue position does not cost one query per job; leave it out
    for a single job.
    """

    error = None
    if job.error_code is not None:
        error = {
            "code": job.error_code,
            "message": job.error_message or job.error_code,
        }
    if queue_positions is None:
        position = queue_position(session, job)
    else:
        position = queue_positions.get(job.id)
        if position is None and job.status == "queued":
            # A queued job missing from the batched ranking has no
            # ``queued_at``; fall back to the exact single-job calculation.
            position = queue_position(session, job)
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "phase": job.phase,
        "input_mode": job.input_mode,
        "attempt": job.attempt,
        "current_stage": job.current_stage,
        "progress": {
            "step": job.progress_step,
            "total_steps": job.progress_total_steps,
            "percent": job.progress_percent,
            "updated_at": job.progress_updated_at,
        },
        "queue_position": position,
        "stages": [
            {
                "name": stage.name,
                "kind": stage.kind,
                "status": stage.status,
                "steps_completed": stage.steps_completed,
                "steps_target": stage.steps_target,
                "attempts": stage.attempts,
                "error": stage.error,
                "started_at": stage.started_at,
                "completed_at": stage.completed_at,
            }
            for stage in job.stages
        ],
        "error": error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "queued_at": job.queued_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def get_owned_job(session: Session, owner_id: str, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.owner_id != owner_id:
        raise APIError(404, "job_not_found", f"Job {job_id!r} was not found")
    return job


def _encode_cursor(job: Job) -> str:
    raw = f"{job.created_at}|{job.id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        created_at, job_id = raw.split("|", 1)
        if not created_at or not job_id:
            raise ValueError
    except (ValueError, UnicodeError) as exc:
        raise APIError(400, "invalid_cursor", "Invalid pagination cursor") from exc
    return created_at, job_id


def list_jobs(
    session: Session,
    owner_id: str,
    *,
    status: str | None,
    limit: int,
    cursor: str | None,
) -> tuple[list[Job], str | None]:
    if status is not None and status not in _JOB_STATUSES:
        raise APIError(400, "invalid_status", f"Unknown job status {status!r}")
    if limit < 1 or limit > 100:
        raise APIError(400, "invalid_limit", "limit must be between 1 and 100")

    # ``selectinload`` loads the stages for the whole page in one extra
    # query.  Without it, serializing a page of jobs lazy-loads the stages
    # one job at a time.
    statement = select(Job).options(selectinload(Job.stages)).where(
        Job.owner_id == owner_id
    )
    if status is not None:
        statement = statement.where(Job.status == status)
    if cursor is not None:
        created_at, job_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Job.created_at < created_at,
                and_(Job.created_at == created_at, Job.id < job_id),
            )
        )
    statement = statement.order_by(Job.created_at.desc(), Job.id.desc()).limit(
        limit + 1
    )
    jobs = list(session.scalars(statement).all())
    next_cursor = None
    if len(jobs) > limit:
        jobs = jobs[:limit]
        next_cursor = _encode_cursor(jobs[-1])
    return jobs, next_cursor


def list_events(
    session: Session, job: Job, *, limit: int, after_id: int | None
) -> list[dict[str, Any]]:
    from ..models import JobEvent

    statement = select(JobEvent).where(JobEvent.job_id == job.id)
    if after_id is not None:
        statement = statement.where(JobEvent.id > after_id)
    statement = statement.order_by(JobEvent.id.asc()).limit(limit)
    events = session.scalars(statement).all()
    return [
        {
            "id": event.id,
            "type": event.type,
            "message": event.message,
            "data": json.loads(event.data_json) if event.data_json else None,
            "created_at": event.created_at,
        }
        for event in events
    ]


def list_events_across_jobs(
    session: Session,
    owner_id: str,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """List recent events across all jobs and prep jobs owned by ``owner_id``.

    MD simulation jobs and system-preparation jobs keep separate event logs
    (``job_events`` is keyed by MD job id, ``prep_events`` by prep job id),
    but the user-facing activity feed shows both.  Events are ordered by
    creation time, newest first.
    """
    from ..models import Job, JobEvent, PrepEvent, PrepJob

    # Both statements are bounded and ordered in SQL.  Fetching the whole
    # event history and truncating in Python made the feed cost grow with
    # the number of events ever recorded for the owner.
    job_statement = (
        select(JobEvent, Job)
        .join(Job, JobEvent.job_id == Job.id)
        .where(Job.owner_id == owner_id)
        .order_by(JobEvent.created_at.desc(), JobEvent.id.desc())
        .limit(limit + 1)
    )
    prep_statement = (
        select(PrepEvent, PrepJob)
        .join(PrepJob, PrepEvent.prep_job_id == PrepJob.id)
        .where(PrepJob.owner_id == owner_id)
        .order_by(PrepEvent.created_at.desc(), PrepEvent.id.desc())
        .limit(limit + 1)
    )

    if cursor is not None:
        try:
            created_at, event_id = cursor.split("|", 1)
            job_statement = job_statement.where(
                or_(
                    JobEvent.created_at < created_at,
                    and_(
                        JobEvent.created_at == created_at,
                        JobEvent.id < int(event_id),
                    ),
                )
            )
            prep_statement = prep_statement.where(
                or_(
                    PrepEvent.created_at < created_at,
                    and_(
                        PrepEvent.created_at == created_at,
                        PrepEvent.id < int(event_id),
                    ),
                )
            )
        except (ValueError, UnicodeError):
            raise APIError(400, "invalid_cursor", "Invalid pagination cursor")

    rows: list[dict[str, Any]] = []
    for event, job in session.execute(job_statement).all():
        rows.append(
            {
                "id": event.id,
                "created_at": event.created_at,
                "source": "job",
                "job_id": event.job_id,
                "job_name": job.name,
                "job_status": job.status,
                "prep_type": None,
                "type": event.type,
                "message": event.message,
                "data": json.loads(event.data_json) if event.data_json else None,
            }
        )
    for event, prep_job in session.execute(prep_statement).all():
        rows.append(
            {
                "id": event.id,
                "created_at": event.created_at,
                "source": "prep",
                "job_id": event.prep_job_id,
                "job_name": prep_job_label(prep_job),
                "job_status": prep_job.status,
                "prep_type": prep_job.type,
                "type": event.type,
                "message": event.message,
                "data": json.loads(event.data_json) if event.data_json else None,
            }
        )

    rows.sort(key=lambda row: (row["created_at"], row["id"]), reverse=True)
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = f"{last['created_at']}|{last['id']}"

    return rows, next_cursor

# ---------------------------------------------------------------------------
# Dry validation
# ---------------------------------------------------------------------------


def validate_job(
    session: Session,
    settings: Settings,
    storage: LocalStorage,
    request: JobCreate,
    owner_id: str,
) -> tuple[dict[str, Any], str]:
    """Resolve and validate a request without creating a job workspace."""

    inputs = _relative_inputs(session, owner_id, request, settings)
    if inputs["mode"] != "pdb_id":
        _check_upload_total(session, inputs, settings)
        for file_id in inputs.get("files", []):
            record = session.get(FileRecord, file_id)
            if record is None:
                raise APIError(404, "file_not_found", f"File {file_id!r} was not found")
            if not storage.absolute_key(record.storage_key).is_file():
                raise APIError(
                    500,
                    "input_file_missing",
                    f"Stored input {record.id} is missing",
                )
    elif not settings.allow_pdb_download:
        raise APIError(
            403,
            "pdb_download_disabled",
            "PDB downloads are disabled on this server",
        )

    canonical = build_canonical_spec(request, inputs, settings)
    with tempfile.TemporaryDirectory(prefix="md-validate-") as temporary:
        root = Path(temporary)
        config_text = build_config_toml(canonical, root, settings)
        config_path = root / "config.toml"
        config_path.write_text(config_text, encoding="utf-8")
        load_workflow_config(config_path)
    return canonical, config_text


def remove_workspace(storage: LocalStorage, owner_id: str, job_id: str) -> None:
    """Best-effort workspace removal (used by tests and future admin tasks)."""

    root = storage.job_root(owner_id, job_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
