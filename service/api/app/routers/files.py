"""Immutable file uploads."""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import APIError
from ..models import FileRecord
from ..schemas import FileInspectOut, FileOut
from ..security import require_owner
from ..services.preview import ensure_preview
from ..services.structure import count_atoms
from ..storage import LocalStorage, StorageError, display_name, file_suffix
from ..timeutils import utcnow_iso

# Inspection is PDB-only; gemmi is used (same dependency as the prep worker).
import gemmi  # noqa: E402

# Standard residue names used to classify components.
_STANDARD_RESNAMES = frozenset(
    {
        "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
        "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
        "HOH", "WAT", "O", "OH2",
        "NA", "CL", "K", "CA", "MG", "ZN", "FE", "CU", "MN", "CO", "NI",
    }
)
_ION_RESNAMES = frozenset({"NA", "CL", "K", "CA", "MG", "ZN", "FE", "CU", "MN", "CO", "NI"})
_WATER_RESNAMES = frozenset({"HOH", "WAT", "O", "OH2"})


def _is_likely_ligand(resname: str) -> bool:
    upper = resname.upper().strip()
    if upper in _STANDARD_RESNAMES:
        return False
    if len(upper) <= 2 and upper.isalpha():
        return False
    return True


def _inspect_pdb(path) -> dict:
    """Inspect a PDB file using gemmi and return a structured summary."""

    structure = gemmi.read_structure(str(path))
    chains: dict[str, dict] = {}
    atom_count = 0
    model_count = 0
    min_pos = None
    max_pos = None

    protein_atoms = 0
    water_atoms = 0
    ion_atoms = 0
    ligand_atoms = 0

    for model in structure:
        model_count += 1
        for chain in model:
            cid = chain.name
            if cid not in chains:
                chains[cid] = {
                    "residues": [],
                    "residue_count": 0,
                    "atom_count": 0,
                }
            chain_info = chains[cid]
            residue_names: list[str] = []
            residue_count = 0
            chain_atom_count = 0

            for residue in chain:
                rname = residue.name.strip().upper()
                residue_names.append(rname)
                residue_count += 1
                res_atoms = 0
                for atom in residue:
                    atom_count += 1
                    chain_atom_count += 1
                    res_atoms += 1
                    pos = atom.pos
                    if min_pos is None:
                        min_pos = [pos.x, pos.y, pos.z]
                        max_pos = [pos.x, pos.y, pos.z]
                    else:
                        min_pos[0] = min(min_pos[0], pos.x)
                        min_pos[1] = min(min_pos[1], pos.y)
                        min_pos[2] = min(min_pos[2], pos.z)
                        max_pos[0] = max(max_pos[0], pos.x)
                        max_pos[1] = max(max_pos[1], pos.y)
                        max_pos[2] = max(max_pos[2], pos.z)

                if rname in _WATER_RESNAMES:
                    water_atoms += res_atoms
                elif rname in _ION_RESNAMES:
                    ion_atoms += res_atoms
                elif rname in _STANDARD_RESNAMES:
                    protein_atoms += res_atoms
                else:
                    ligand_atoms += res_atoms

            chain_info["residues"] = sorted(set(residue_names))
            chain_info["residue_count"] = residue_count
            chain_info["atom_count"] = chain_atom_count

    bounding_box = None
    if min_pos is not None and max_pos is not None:
        bounding_box = {
            "min": {"x": min_pos[0], "y": min_pos[1], "z": min_pos[2]},
            "max": {"x": max_pos[0], "y": max_pos[1], "z": max_pos[2]},
        }

    return {
        "chains": chains,
        "ligands": sorted(
            {
                rname
                for info in chains.values()
                for rname in info["residues"]
                if _is_likely_ligand(rname)
            }
        ),
        "components": {
            "protein": protein_atoms,
            "water": water_atoms,
            "ion": ion_atoms,
            "ligand": ligand_atoms,
        },
        "atom_count": atom_count,
        "model_count": model_count,
        "bounding_box": bounding_box,
    }

router = APIRouter(prefix="/files", tags=["files"])

CHUNK_SIZE = 1024 * 1024


@router.post("", response_model=FileOut, status_code=201)
def upload_file(
    request: Request,
    file: UploadFile = File(...),
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileOut:
    # This handler is synchronous on purpose.  It reads and writes the upload
    # on disk, and a synchronous endpoint runs in the threadpool instead of
    # on the event loop, so a large upload does not stall other requests.
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
        destination = storage.upload_path(owner, file_id, safe_name)
    except StorageError as exc:  # pragma: no cover - defensive
        raise APIError(400, "invalid_filename", str(exc)) from exc
    temporary = destination.with_name(destination.name + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while True:
                chunk = file.file.read(CHUNK_SIZE)
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
        file.file.close()

    # Bound the cost of the upload before it can ever reach the queue.  The
    # simulation cost grows with the atom count, so a byte limit alone does
    # not bound the GPU time.
    atom_count = count_atoms(destination, suffix)
    if atom_count is not None and atom_count > settings.max_upload_atoms:
        destination.unlink(missing_ok=True)
        # Leave nothing behind: the upload directory is created for the
        # file, and an empty directory would outlive the rejected upload.
        storage.prune_empty_upload_dirs(owner, file_id)
        raise APIError(
            413,
            "too_many_atoms",
            "Uploaded structure exceeds the atom limit",
            {
                "limit": settings.max_upload_atoms,
                "atoms": atom_count,
            },
        )

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
        storage_key=storage.upload_key(owner, file_id, safe_name),
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


# Inline preview is restricted to structure formats with non-HTML content
# types; combined with nosniff this keeps uploads inside the CSP threat
# model (never user-supplied text rendered as a page).
PREVIEW_CONTENT_TYPES = {
    ".pdb": "chemical/x-pdb",
    ".cif": "chemical/x-cif",
    ".mmcif": "chemical/x-cif",
    ".sdf": "chemical/x-mdl-sdfile",
    ".mol": "chemical/x-mdl-molfile",
    ".mol2": "chemical/x-mol2",
}


def _preview_response(
    request: Request,
    file_id: str,
    owner: str,
    session: Session,
) -> FileResponse:
    """Resolve the structure to serve for a preview.

    Uploads are small structure files; the size guard keeps anything large
    download-only — big systems are meant to be seen through worker-derived
    views, never the raw bytes.

    A file above the guard gets a derived *preview* instead: the solvent and
    ions are removed so a membrane-embedded system can still be looked at in
    the browser.  Without that the viewer would be handed a JSON error and
    render an empty scene.
    """

    record = session.get(FileRecord, file_id)
    if record is None or record.owner_id != owner:
        raise APIError(404, "file_not_found", f"File {file_id!r} was not found")

    settings = request.app.state.settings
    storage = request.app.state.storage

    try:
        path = storage.absolute_key(record.storage_key)
    except StorageError as exc:
        raise APIError(
            404, "file_not_found", "Stored file is unavailable"
        ) from exc
    if not path.is_file():
        raise APIError(404, "file_not_found", "Stored file is unavailable")

    media_type = PREVIEW_CONTENT_TYPES.get(
        path.suffix.lower(), "application/octet-stream"
    )

    if record.size_bytes > settings.max_preview_bytes:
        derived = ensure_preview(
            path,
            storage.preview_path(owner, file_id),
            max_atoms=settings.max_preview_atoms,
        )
        if derived is None:
            raise APIError(
                409,
                "file_too_large_to_preview",
                "This upload is too large to render directly in the browser",
                {
                    "limit": settings.max_preview_bytes,
                    "size_bytes": record.size_bytes,
                },
            )
        path = derived
        # A derived preview is always written as PDB, whatever the source
        # format was, so the client learns the format from this header.
        media_type = PREVIEW_CONTENT_TYPES[".pdb"]

    return FileResponse(
        path,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{file_id}/preview")
def preview_file(
    request: Request,
    file_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    """Serve a structure for direct rendering in the browser."""

    return _preview_response(request, file_id, owner, session)


@router.head("/{file_id}/preview", include_in_schema=False)
def preview_file_head(
    request: Request,
    file_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileResponse:
    """Return the preview headers without the body.

    The viewer asks for the headers first: Mol* does not fail on a response
    that is not a structure, it parses the body, finds no atoms and leaves an
    empty scene behind.  A HEAD request turns that into a visible error.
    """

    return _preview_response(request, file_id, owner, session)


@router.get("/{file_id}/inspect", response_model=FileInspectOut)
def inspect_file(
    request: Request,
    file_id: str,
    owner: str = Depends(require_owner),
    session: Session = Depends(get_session),
) -> FileInspectOut:
    """Return a structure summary for an upload: chains, residues, components,
    atom count, model count, and bounding box. PDB files only."""

    record = session.get(FileRecord, file_id)
    if record is None or record.owner_id != owner:
        raise APIError(404, "file_not_found", f"File {file_id!r} was not found")

    settings = request.app.state.settings
    if record.size_bytes > settings.max_upload_bytes:
        raise APIError(
            413,
            "file_too_large_to_inspect",
            "This upload is too large to inspect",
            {"limit": settings.max_upload_bytes, "size_bytes": record.size_bytes},
        )

    storage = request.app.state.storage
    try:
        path = storage.absolute_key(record.storage_key)
    except StorageError as exc:
        raise APIError(
            404, "file_not_found", "Stored file is unavailable"
        ) from exc
    if not path.is_file():
        raise APIError(404, "file_not_found", "Stored file is unavailable")

    if path.suffix.lower() != ".pdb":
        raise APIError(
            400,
            "unsupported_file_type",
            "Inspection is only available for PDB files",
        )

    return FileInspectOut(**_inspect_pdb(path))
