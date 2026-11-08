"""Stage-manifest reconciliation and artifact scanning.

``stage.json`` is the authoritative completion record written by the
simulation.  After the subprocess exits the worker reads those manifests and
reports them to the API.  The filesystem scan below only lists regular files
inside the job root; symlinks and temporary files are ignored.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

STAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

STAGE_STATUSES = frozenset(
    {"pending", "running", "completed", "failed", "canceled", "skipped"}
)

ARTIFACT_KINDS = frozenset(
    {
        "config",
        "log",
        "state",
        "checkpoint",
        "trajectory",
        "structure",
        "metadata",
    }
)

_LOG_SUFFIXES = frozenset({".log", ".out", ".err", ".stdout", ".stderr"})
_STATE_SUFFIXES = frozenset({".xml"})
_CHECKPOINT_SUFFIXES = frozenset({".chk"})
_TRAJECTORY_SUFFIXES = frozenset({".dcd", ".trr", ".xtc"})
_STRUCTURE_SUFFIXES = frozenset({".pdb", ".cif", ".mmcif", ".mol", ".mol2", ".sdf"})
_SKIP_SUFFIXES = frozenset({".tmp", ".part"})


@dataclass(frozen=True)
class StageManifest:
    name: str
    status: str
    steps_completed: int
    attempts: int
    error: str | None
    data: dict[str, Any]

    @property
    def signature(self) -> tuple[Any, ...]:
        return (
            self.status,
            self.steps_completed,
            self.attempts,
            self.error,
            self.data,
        )


@dataclass(frozen=True)
class ScannedArtifact:
    stage_name: str | None
    kind: str
    relative_path: str


def _confined_regular_file(root: Path, relative: PurePosixPath) -> Path | None:
    """Return a real file below ``root``, rejecting symlinks and escapes."""

    if relative.is_absolute() or not relative.parts:
        return None
    if any(part in ("", ".", "..") for part in relative.parts):
        return None

    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    if not resolved.is_file():
        return None
    return resolved


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def read_stage_manifest(job_root: Path, name: str) -> StageManifest | None:
    if not STAGE_NAME_RE.match(name):
        return None
    relative = PurePosixPath("outputs", "stages", name, "stage.json")
    path = _confined_regular_file(job_root, relative)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    status = data.get("status")
    if status not in STAGE_STATUSES:
        status = "failed"
    error = data.get("error")
    if not isinstance(error, str):
        error = None
    return StageManifest(
        name=name,
        status=status,
        steps_completed=_int(data.get("steps_completed")),
        attempts=max(1, _int(data.get("attempt"), default=1)),
        error=error[:8000] if error else None,
        data=data,
    )


def remove_stage_manifest(job_root: Path, name: str) -> bool:
    """Delete one confined, regular stage manifest.

    Returns True when a file was removed.  Symlinks, directories, and paths
    outside the job root are left alone; callers never need to trust the
    workspace.  A missing manifest is not an error.
    """

    if not STAGE_NAME_RE.match(name):
        return False
    relative = PurePosixPath("outputs", "stages", name, "stage.json")
    path = _confined_regular_file(job_root, relative)
    if path is None:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def read_stage_manifests(
    job_root: Path, stage_names: list[str] | tuple[str, ...]
) -> dict[str, StageManifest]:
    """Read each known stage manifest in execution order."""

    manifests: dict[str, StageManifest] = {}
    for name in stage_names:
        manifest = read_stage_manifest(job_root, name)
        if manifest is not None:
            manifests[name] = manifest
    return manifests


def artifact_kind(relative_path: str) -> str:
    pure = PurePosixPath(relative_path)
    name = pure.name.lower()
    suffix = pure.suffix.lower()
    if name == "config.toml":
        return "config"
    if suffix in _LOG_SUFFIXES:
        return "log"
    if suffix in _STATE_SUFFIXES:
        return "state"
    if suffix in _CHECKPOINT_SUFFIXES:
        return "checkpoint"
    if suffix in _TRAJECTORY_SUFFIXES:
        return "trajectory"
    if suffix in _STRUCTURE_SUFFIXES:
        return "structure"
    return "metadata"


def _stage_for_path(relative_path: str, stage_names: frozenset[str]) -> str | None:
    parts = PurePosixPath(relative_path).parts
    if len(parts) >= 4 and parts[0] == "outputs" and parts[1] == "stages":
        if parts[2] in stage_names:
            return parts[2]
    return None


def scan_artifacts(
    job_root: Path,
    stage_names: list[str] | tuple[str, ...],
    *,
    max_files: int = 2000,
) -> list[ScannedArtifact]:
    """List regular files relative to the job root.

    Directory symlinks are not followed, file symlinks are skipped, and the
    result is capped so a pathological workspace cannot exceed the internal
    protocol's artifact limit.
    """

    root = Path(job_root).resolve()
    if not root.is_dir():
        return []
    known_stages = frozenset(stage_names)
    artifacts: list[ScannedArtifact] = []

    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not (Path(directory) / name).is_symlink()
        )
        for filename in sorted(filenames):
            if filename.endswith(tuple(_SKIP_SUFFIXES)):
                continue
            path = Path(directory) / filename
            if path.is_symlink():
                continue
            try:
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
            artifacts.append(
                ScannedArtifact(
                    stage_name=_stage_for_path(relative, known_stages),
                    kind=artifact_kind(relative),
                    relative_path=relative,
                )
            )
            if len(artifacts) >= max_files:
                return artifacts
    return artifacts


def tail_text(path: Path, *, max_chars: int = 4000) -> str:
    """Return the tail of a log file, tolerating binary or missing files."""

    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_chars * 4))
            data = handle.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace").strip()
    return text[-max_chars:]
