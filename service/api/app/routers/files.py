"""Immutable file uploads."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import FileRecord
from ..schemas import FileOut
from ..security import require_owner
from ..storage import StorageError, display_name, file_suffix
from ..timeutils import utcnow_iso

router = APIRouter(prefix="/files", tags=["files"])

CHUNK_SIZE = 1024 * 1024


@router.post("", response_model=FileOut, status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileOut:
    settings = request.app.state.settings
    storage = request.app.state.storage

    original_name = file.filename or ""
    if not original_name:
        raise APIError(400, "missing_filename", "Upload must include a filename")
    try:
        suffix = file_suffix(original_name)
    except StorageError as exc:
        raise APIError(400, "unsupported_file_type", str(exc)) from exc

    safe_name = display_name(original_name)
    if not safe_name.lower().endswith(suffix):
        safe_name = f"upload{suffix}"

    file_id = str(uuid.uuid4())
    try:
        destination = storage.upload_path(file_id, safe_name)
    except StorageError as exc:  # pragma: no cover - defensive
        raise APIError(400, "invalid_filename", str(exc)) from exc
    temporary = destination.with_name(destination.name + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise APIError(
                        413,
                        "upload_too_large",
                        "Upload exceeds the per-file size limit",
                        {"limit": settings.max_upload_bytes, "size_bytes": size},
                    )
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise APIError(400, "empty_upload", "Uploaded file is empty")
        temporary.replace(destination)
    except APIError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise APIError(500, "upload_failed", f"Could not store upload: {exc}") from exc
    finally:
        await file.close()

    record = FileRecord(
        id=file_id,
        owner_id=owner,
        original_name=(
            original_name.replace("\\", "/").rsplit("/", 1)[-1][:255]
            or safe_name
        ),
        content_type=(file.content_type or "application/octet-stream")[:128],
        size_bytes=size,
        sha256=digest.hexdigest(),
        storage_key=storage.upload_key(file_id, safe_name),
        created_at=utcnow_iso(),
    )
    try:
        session.add(record)
        session.commit()
    except BaseException:
        session.rollback()
        destination.unlink(missing_ok=True)
        raise

    return FileOut(
        id=record.id,
        name=record.original_name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        content_type=record.content_type,
        created_at=record.created_at,
    )


@router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileOut:
    record = session.get(FileRecord, file_id)
    if record is None or record.owner_id != owner:
        raise APIError(404, "file_not_found", f"File {file_id!r} was not found")
    return FileOut(
        id=record.id,
        name=record.original_name,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        content_type=record.content_type,
        created_at=record.created_at,
    )
