"""Local filesystem storage with strict path confinement.

The database stores only paths relative to ``DATA_ROOT``.  Every read and write
goes through this module, which rejects absolute paths, traversal components,
and symlinks.  Replacing this class with an object-storage implementation later
should not require changing the job model.

Everything an account owns lives under ``DATA_ROOT/users/<owner_id>/``:

    users/<owner_id>/uploads/<file_id>/<name>   uploaded structures
    users/<owner_id>/jobs/<job_id>/             simulation workspaces
    users/<owner_id>/prep/<prep_job_id>/        system-preparation workspaces

The account id is part of the path as well as part of every database row, so
a mistake in an ownership check cannot reach another account's files.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath

from .settings import Settings

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

PROTEIN_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif"})
LIGAND_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif", ".sdf", ".mol", ".mol2"})
ALLOWED_SUFFIXES = PROTEIN_SUFFIXES | LIGAND_SUFFIXES

# Name of the cached, browser-sized preview next to an upload.
PREVIEW_FILENAME = "preview.pdb"


class StorageError(ValueError):
    """Raised when a stored path is invalid or escapes the data root."""


def validate_id(value: str, label: str = "id") -> str:
    if not _ID_RE.match(value or ""):
        raise StorageError(f"Invalid {label}")
    return value


def file_suffix(original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise StorageError(f"Unsupported file type {suffix!r}; allowed: {allowed}")
    return suffix


def display_name(original_name: str) -> str:
    """Return a safe basename for display and storage."""

    name = Path(original_name.replace("\\", "/")).name
    name = _SAFE_NAME_RE.sub("_", name).strip("._")
    if not name:
        name = "upload"
    if len(name) > 180:
        suffix = Path(name).suffix[:20]
        stem = Path(name).stem[: 180 - len(suffix)]
        name = stem + suffix
    return name


class LocalStorage:
    """Path helper rooted at one persistent data directory."""

    def __init__(self, settings: Settings):
        self.root = settings.data_root.expanduser().resolve()
        self.users = self.root / "users"
        self.cache = self.root / "cache"

    # -- Layout -----------------------------------------------------------

    def ensure_layout(self) -> None:
        for directory in (self.users, self.cache):
            directory.mkdir(parents=True, exist_ok=True)

    def owner_root(self, owner_id: str) -> Path:
        """The directory that holds everything one account owns."""

        validate_id(owner_id, "owner id")
        return self.users / owner_id

    def owner_uploads(self, owner_id: str) -> Path:
        return self.owner_root(owner_id) / "uploads"

    def owner_jobs(self, owner_id: str) -> Path:
        return self.owner_root(owner_id) / "jobs"

    def owner_prep(self, owner_id: str) -> Path:
        return self.owner_root(owner_id) / "prep"

    def upload_key(self, owner_id: str, file_id: str, safe_name: str) -> str:
        validate_id(owner_id, "owner id")
        validate_id(file_id, "file id")
        return f"users/{owner_id}/uploads/{file_id}/{safe_name}"

    def upload_path(self, owner_id: str, file_id: str, safe_name: str) -> Path:
        return self.absolute_key(self.upload_key(owner_id, file_id, safe_name))

    def upload_dir(self, owner_id: str, file_id: str) -> Path:
        """The directory that holds one upload and its derived views."""

        validate_id(owner_id, "owner id")
        validate_id(file_id, "file id")
        return self.owner_uploads(owner_id) / file_id

    def preview_path(self, owner_id: str, file_id: str) -> Path:
        """Where the browser-sized preview of an upload is cached."""

        return self.upload_dir(owner_id, file_id) / PREVIEW_FILENAME

    def job_root(self, owner_id: str, job_id: str) -> Path:
        validate_id(owner_id, "owner id")
        validate_id(job_id, "job id")
        return self.owner_jobs(owner_id) / job_id

    def job_temp_root(self, owner_id: str, job_id: str) -> Path:
        """The staging directory a job workspace is built in."""

        return self.owner_jobs(owner_id) / f".{job_id}.tmp"

    def prune_empty_upload_dirs(self, owner_id: str, file_id: str) -> None:
        """Remove the directories an upload leaves behind when it fails.

        A rejected upload must not leave a directory tree behind, not even
        an empty one: the account's directory would otherwise look like it
        holds data when it does not.
        """

        for directory in (
            self.upload_dir(owner_id, file_id),
            self.owner_uploads(owner_id),
            self.owner_root(owner_id),
        ):
            try:
                if directory.is_dir() and not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                continue

    # -- Confinement ------------------------------------------------------

    def _confined_path(self, root: Path, relative_key: str) -> Path:
        """Resolve a relative path inside ``root`` and reject escapes."""

        pure = PurePosixPath(relative_key)
        if pure.is_absolute() or not pure.parts:
            raise StorageError("Path must be relative")
        parts = pure.parts
        if any(part in ("", ".", "..") for part in parts):
            raise StorageError(
                "Path must not contain empty, '.' or '..' components"
            )
        if "\x00" in relative_key:
            raise StorageError("Path must not contain NUL bytes")

        candidate = root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise StorageError("Symbolic links are not allowed")

        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise StorageError("Path escapes its root")
        return resolved

    def absolute_key(self, relative_key: str) -> Path:
        """Resolve a database-relative path inside ``DATA_ROOT``.

        Symlinks are rejected at every component so a path that ultimately
        resolves inside the root cannot be used to escape it.
        """

        return self._confined_path(self.root, relative_key)

    def job_path(self, owner_id: str, job_id: str, relative_path: str) -> Path:
        """Resolve a path relative to one job workspace."""

        return self._confined_path(
            self.job_root(owner_id, job_id), relative_path
        )

    def relative_key(self, path: Path) -> str:
        resolved = path.resolve()
        if self.root not in resolved.parents and resolved != self.root:
            raise StorageError("Path escapes the data root")
        return resolved.relative_to(self.root).as_posix()

    # -- File helpers -----------------------------------------------------

    def write_text_atomic(self, path: Path, text: str) -> None:
        self._assert_parent_inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    def write_bytes_atomic(self, path: Path, data: bytes) -> None:
        self._assert_parent_inside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)

    def copy_file(self, source: Path, destination: Path) -> None:
        self._assert_parent_inside(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(destination)

    def remove_tree(self, path: Path) -> None:
        self._assert_parent_inside(path)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _assert_parent_inside(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise StorageError("Path escapes the data root")
