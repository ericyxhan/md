"""System-preparation service: membrane embedding queue and file validation.

Prep jobs are queued through the public API and executed by a dedicated prep
worker process.  This module validates input files before queuing and registers
prep job output files when a worker reports completion.
"""

from __future__ import annotations

import hashlib
import httpx
import json
import re
import shutil
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from ..db import create_db_engine, create_session_factory, write_transaction
from ..errors import APIError
from ..models import FileRecord, PrepJob
from ..schemas import SystemPrepStep
from ..settings import Settings, get_settings
from ..storage import LocalStorage, display_name
from ..timeutils import utcnow_iso


@contextmanager
def _session_scope(
    settings: Settings,
    session_factory: sessionmaker[Session] | None = None,
) -> Iterator[sessionmaker[Session]]:
    """Yield a session factory and release any engine created here.

    The API process already owns an engine (``app.state.engine``).  Callers
    that do not pass one get a throwaway engine, which is disposed on the
    way out so its connection pool is not leaked.
    """

    if session_factory is not None:
        yield session_factory
        return

    engine = create_db_engine(settings)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def prep_job_label(prep_job: PrepJob) -> str:
    """A friendly label for a prep job.

    Prep jobs have no name column, so one is derived from the request: the
    lipid for a membrane embedding, the caller's name for a system prep.
    """
    try:
        request = json.loads(prep_job.request_json)
    except (ValueError, TypeError):
        request = {}
    if prep_job.type == "membrane_embed":
        lipid = request.get("lipid")
        return f"Membrane embedding · {lipid}" if lipid else "Membrane embedding"
    name = request.get("name")
    return name or "System preparation"

# Supported protein structure suffixes for membrane embedding.
PREP_INPUT_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif"})

# PDB header magic for content validation.
_PDB_HEADER_RE = re.compile(
    r"^(HEADER|MODEL|TITLE|COMPND|SOURCE|ATOM|HETATM)", re.MULTILINE
)
_CIF_HEADER_RE = re.compile(
    r"^(data_|#|loop_|_atom|_chem|_cell|_symmetry)", re.MULTILINE
)


def _validate_pdb_content(path: Path) -> None:
    """Best-effort validation that a file looks like a PDB."""

    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return  # Can't read; let packmol-memgen report its own error
    text = chunk.decode("utf-8", errors="replace")
    if not _PDB_HEADER_RE.search(text):
        raise APIError(
            400,
            "invalid_pdb_content",
            "File does not appear to be a valid PDB structure",
        )


def _validate_cif_content(path: Path) -> None:
    """Best-effort validation that a file looks like mmCIF."""

    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return
    text = chunk.decode("utf-8", errors="replace")
    if not _CIF_HEADER_RE.search(text):
        raise APIError(
            400,
            "invalid_cif_content",
            "File does not appear to be a valid mmCIF structure",
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_output_files(
    *,
    storage: LocalStorage,
    owner: str,
    output_paths: list[Path],
) -> list[FileRecord]:
    """Copy prep outputs into the uploads store and describe them.

    This does the slow part — reading every output to hash it and copying it
    into the uploads store — and returns the records to insert.  It is
    deliberately separate from the database write so the caller can do it
    before taking the process-wide write lock.
    """

    records: list[FileRecord] = []
    for source_path in output_paths:
        if not source_path.is_file():
            continue
        file_id = str(uuid.uuid4())
        safe_name = display_name(source_path.name)
        destination = storage.upload_path(owner, file_id, safe_name)
        destination.parent.mkdir(parents=True, exist_ok=True)

        size = source_path.stat().st_size
        digest = _sha256_file(source_path)
        storage.copy_file(source_path, destination)

        content_type = (
            "chemical/x-pdb"
            if source_path.suffix.lower() == ".pdb"
            else "chemical/x-cif"
        )
        records.append(
            FileRecord(
                id=file_id,
                owner_id=owner,
                original_name=source_path.name[:255],
                content_type=content_type[:128],
                size_bytes=size,
                sha256=digest,
                storage_key=storage.upload_key(owner, file_id, safe_name),
                created_at=utcnow_iso(),
            )
        )

    return records


def validate_prep_input(
    *,
    storage: LocalStorage,
    session: Session,
    protein_file_id: str,
    owner: str,
) -> Path:
    """Validate that the input file exists, is owned, and has valid content.

    Returns the absolute path to the source file.
    """

    from ..models import FileRecord

    file_record = session.get(FileRecord, protein_file_id)
    if file_record is None or file_record.owner_id != owner:
        raise APIError(
            404, "file_not_found", f"Source file {protein_file_id} not found"
        )

    source_path = storage.absolute_key(file_record.storage_key)
    if not source_path.is_file():
        raise APIError(
            500, "input_file_missing", f"Stored input {protein_file_id} is missing"
        )

    suffix = source_path.suffix.lower()
    if suffix not in PREP_INPUT_SUFFIXES:
        raise APIError(
            400,
            "unsupported_file_type",
            f"Unsupported protein format {suffix!r}; use PDB or mmCIF",
        )

    if suffix == ".pdb":
        _validate_pdb_content(source_path)
    elif suffix in {".cif", ".mmcif"}:
        _validate_cif_content(source_path)

    return source_path


def queue_membrane_embed(
    *,
    prep_job_id: str,
    owner: str,
    protein_file_id: str,
    lipid: str,
    box_padding_nm: float,
    orientation: str | None,
    ionic_strength_molar: float,
    settings: Settings | None = None,
    storage: LocalStorage | None = None,
) -> None:
    """Queue a membrane embedding job.

    This validates the input file exists and is readable, then leaves the job
    in ``queued`` status for the prep worker to claim and execute.
    """

    settings = settings or get_settings()
    if not settings.packmol_path:
        with _session_scope(settings) as factory:
            with closing(factory()) as session:
                with write_transaction(session):
                    job = session.get(PrepJob, prep_job_id)
                    if job is not None:
                        job.status = "failed"
                        job.error_message = (
                            "packmol_path is not configured on this server"
                        )
                        job.completed_at = utcnow_iso()
                        job.updated_at = utcnow_iso()
        return

    storage = storage or LocalStorage(settings)

    # Validate the input file before queuing
    with _session_scope(settings) as factory:
        with closing(factory()) as session:
            source_path = validate_prep_input(
                storage=storage,
                session=session,
                protein_file_id=protein_file_id,
                owner=owner,
            )
            job = session.get(PrepJob, prep_job_id)
            if job is None:
                return
            job.status = "queued"
            job.updated_at = utcnow_iso()
            session.commit()

    # The prep worker will claim this job and execute packmol-memgen.
    # Nothing more to do here.


def finish_prep_job(
    *,
    prep_job_id: str,
    owner: str,
    status: str,
    output_paths: list[Path],
    error_code: str | None = None,
    error_message: str | None = None,
    settings: Settings | None = None,
    storage: LocalStorage | None = None,
) -> None:
    """Register prep job output files and mark the job as completed/failed.

    Called by the internal prep router after the worker reports completion.
    """

    settings = settings or get_settings()
    storage = storage or LocalStorage(settings)

    # Check the job before copying anything, so a job that does not exist
    # (or belongs to somebody else) does not leave copies behind.
    with _session_scope(settings) as factory:
        with closing(factory()) as session:
            job = session.get(PrepJob, prep_job_id)
            if job is None or job.owner_id != owner:
                return

    # Copy and hash the outputs before taking the write lock: reading and
    # copying a large structure is slow, and the lock serializes every
    # state change in the API.
    records: list[FileRecord] = []
    if status == "completed" and output_paths:
        records = _copy_output_files(
            storage=storage,
            owner=owner,
            output_paths=output_paths,
        )

    with _session_scope(settings) as factory:
        with closing(factory()) as session:
            with write_transaction(session):
                job = session.get(PrepJob, prep_job_id)
                if job is None or job.owner_id != owner:
                    return

                job.status = status
                job.updated_at = utcnow_iso()
                job.completed_at = utcnow_iso()

                if status == "failed":
                    job.error_code = error_code or "prep_failed"
                    job.error_message = error_message or "Prep job failed"

                file_ids: list[str] = []
                for record in records:
                    session.add(record)
                    file_ids.append(record.id)
                if file_ids:
                    session.flush()
                    job.output_file_ids = json.dumps(file_ids)

                job.result_json = json.dumps(
                    {
                        "output_file_ids": file_ids,
                        "error_code": error_code,
                        "error_message": error_message,
                    },
                    separators=(",", ":"),
                )


_RCSB_URL = "https://files.rcsb.org/download/{pdb_id}.pdb"
_PDB_ID_RE = re.compile(r"^[0-9A-Za-z]{4}$")


def _download_pdb(
    pdb_id: str, destination: Path, settings: Settings
) -> int:
    """Download a PDB from RCSB to *destination*.  Returns bytes written."""
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


def fetch_pdb_file(
    *,
    pdb_id: str,
    owner: str,
    settings: Settings | None = None,
    storage: LocalStorage | None = None,
) -> str:
    """Download a PDB from RCSB and register it as a FileRecord.

    Returns the file_id of the registered file.
    """

    settings = settings or get_settings()
    storage = storage or LocalStorage(settings)

    if not settings.allow_pdb_download:
        raise APIError(
            403,
            "pdb_download_disabled",
            "PDB downloads are disabled on this server",
        )
    if not _PDB_ID_RE.match(pdb_id):
        raise APIError(422, "invalid_pdb_id", "PDB ID must be four characters")

    pdb_id = pdb_id.upper()
    download_dir = storage.cache / "pdb-downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    dest = download_dir / f"{pdb_id}.pdb"

    _download_pdb(pdb_id, dest, settings)

    # Register the downloaded file as a FileRecord.
    file_id = str(uuid.uuid4())
    safe_name = display_name(dest.name)
    digest = hashlib.sha256()
    with dest.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    # Copy to the canonical storage location so the artifact route can find it.
    canonical_dest = storage.upload_path(owner, file_id, safe_name)
    canonical_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dest, canonical_dest)

    record = FileRecord(
        id=file_id,
        owner_id=owner,
        original_name=dest.name[:255],
        content_type="chemical/x-pdb",
        size_bytes=canonical_dest.stat().st_size,
        sha256=digest.hexdigest(),
        storage_key=storage.upload_key(owner, file_id, safe_name),
        created_at=utcnow_iso(),
    )

    with _session_scope(settings) as factory:
        with factory() as session:
            session.add(record)
            session.commit()

    return file_id


def queue_system_prep(
    *,
    prep_job_id: str,
    owner: str,
    input_file_id: str | None,
    pdb_id: str | None,
    steps: list[SystemPrepStep],
    settings: Settings | None = None,
    storage: LocalStorage | None = None,
) -> None:
    """Queue a system-preparation job (remove_ligand, select_chain, add_ligand).

    Validates input files and downloads PDB IDs if needed, then leaves the job
    in ``queued`` status for the prep worker to claim and execute.
    """

    settings = settings or get_settings()
    storage = storage or LocalStorage(settings)

    # Resolve the input to an absolute path.
    source_path: Path | None = None
    with _session_scope(settings) as session_factory:
        with session_factory() as session:
            if pdb_id:
                # Download PDB into the cache store as a normal file record.
                download_dir = storage.cache / "pdb-downloads"
                download_dir.mkdir(parents=True, exist_ok=True)
                dest = download_dir / f"{pdb_id.upper()}.pdb"
                _download_pdb(pdb_id, dest, settings)

                # Register the downloaded file as a FileRecord.
                file_id = str(uuid.uuid4())
                safe_name = display_name(dest.name)
                record = FileRecord(
                    id=file_id,
                    owner_id=owner,
                    original_name=dest.name[:255],
                    content_type="chemical/x-pdb",
                    size_bytes=dest.stat().st_size,
                    sha256="",  # filled below
                    storage_key=storage.upload_key(owner, file_id, safe_name),
                    created_at=utcnow_iso(),
                )
                # Compute sha256 after writing.
                digest = hashlib.sha256()
                with dest.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                record.sha256 = digest.hexdigest()
                session.add(record)
                session.flush()
                input_file_id = file_id
                source_path = storage.absolute_key(record.storage_key)
            elif input_file_id:
                file_record = session.get(FileRecord, input_file_id)
                if file_record is None or file_record.owner_id != owner:
                    raise APIError(
                        404, "file_not_found", f"File {input_file_id!r} not found"
                    )
                source_path = storage.absolute_key(file_record.storage_key)
                if not source_path.is_file():
                    raise APIError(
                        500, "input_file_missing", f"Stored input {input_file_id} is missing"
                    )

            # Validate ligand file IDs for add_ligand steps.
            for step in steps:
                if step.operation == "add_ligand":
                    for ligand_id in step.ligand_file_ids:
                        ligand_record = session.get(FileRecord, ligand_id)
                        if ligand_record is None or ligand_record.owner_id != owner:
                            raise APIError(
                                404,
                                "file_not_found",
                                f"Ligand file {ligand_id!r} not found",
                            )
                        ligand_path = storage.absolute_key(ligand_record.storage_key)
                        if not ligand_path.is_file():
                            raise APIError(
                                500,
                                "input_file_missing",
                                f"Stored ligand {ligand_id} is missing",
                            )

            # Validate input is a PDB (system prep ops work on PDB).
            if source_path is not None:
                suffix = source_path.suffix.lower()
                if suffix != ".pdb":
                    raise APIError(
                        400,
                        "unsupported_file_type",
                        f"System preparation requires a PDB file, got {suffix!r}",
                    )
                _validate_pdb_content(source_path)

            job = session.get(PrepJob, prep_job_id)
            if job is None:
                return
            job.status = "queued"
            job.updated_at = utcnow_iso()
            session.commit()
