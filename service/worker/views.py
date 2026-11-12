"""Derive browser-friendly views of a job's structures and time series.

The prepared system is a solvated box: hundreds of thousands of atoms, the
large majority waters and ions.  Shipping that to a browser is slow and
useless for orientation.  This module derives a *view* next to the canonical
artifacts under ``outputs/views/``:

    outputs/views/prepared/
      view.pdb         solute-focused structure (waters/ions stripped)
      components.json  composition summary + provenance for captions

Per completed simulation stage with a trajectory:

    outputs/views/<stage>/
      view.pdb         solute topology (paired 1:1 with view.dcd)
      view.dcd         stride-limited, solute-focused trajectory
      frames.json      frame_count, stride, dt_ps, atom_count, provenance
      final.pdb        snapshot of the last frame (checkpoint inspector)

Per completed simulation stage with a state log:

    outputs/analysis/series.json
      downsampled (<= 2,000 points) time series from simulation.log for charting

Views are cosmetic derivatives: generation failures must never fail a job,
files are regenerated only when the source changes, and the raw artifacts
remain the source of truth.  The module optionally depends on mdtraj for
trajectory slicing; if mdtraj is unavailable, trajectory views are skipped
without failing the job.
"""

from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Any

try:
    import mdtraj as md

    _MDTRAJ_AVAILABLE = True
except ImportError:  # pragma: no cover - mdtraj is a V3 requirement
    md = None  # type: ignore[assignment]
    _MDTRAJ_AVAILABLE = False

# Residue names treated as solvent when classifying HETATM records.
WATER_RESNAMES = frozenset(
    {"HOH", "WAT", "H2O", "OH2", "D3O", "DOD", "TIP", "TIP3", "TIP4", "SOL"}
)

# Residue names treated as ions (OpenMM writes NA/CL for NaCl).
ION_RESNAMES = frozenset(
    {
        "NA", "CL", "K", "CA", "MG", "ZN", "FE", "FE2", "CU", "CU1", "MN",
        "MN3", "CO", "NI", "BR", "I", "IOD", "F", "LI", "RB", "CS", "NA+",
        "CL-", "K+", "SOD", "POT", "CAL", "CLA",
    }
)

DEFAULT_MAX_VIEW_ATOMS = 25_000
DEFAULT_MAX_FRAMES = 240
DEFAULT_MAX_DCD_MB = 15
DEFAULT_MAX_SERIES_POINTS = 2_000

_PREPARED_SOURCE = Path("outputs") / "metadata" / "prepared.pdb"
_VIEW_DIR = Path("outputs") / "views" / "prepared"
_STAGES_DIR = Path("outputs") / "stages"
_ANALYSIS_DIR = Path("outputs") / "analysis"


def _resname(line: str) -> str:
    return line[17:20].strip().upper()


def _parse_box(line: str) -> dict[str, float] | None:
    """Extract cell constants from a CRYST1 record."""

    try:
        return {
            "a": float(line[6:15]),
            "b": float(line[15:24]),
            "c": float(line[24:33]),
            "alpha": float(line[33:40]),
            "beta": float(line[40:47]),
            "gamma": float(line[47:54]),
        }
    except ValueError:
        return None


def _source_signature(path: Path) -> tuple[int, float]:
    stat = path.stat()
    return (stat.st_size, stat.st_mtime)


def _write_json_if_changed(path: Path, data: Any) -> bool:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except (OSError, UnicodeError):
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return True


# ---------------------------------------------------------------------------
# Prepared-system view (V1, stdlib PDB parsing)
# ---------------------------------------------------------------------------


def generate_prepared_view(
    job_root: Path,
    *,
    max_view_atoms: int = DEFAULT_MAX_VIEW_ATOMS,
) -> list[Path]:
    """Write ``outputs/views/prepared`` for the prepared system, when present.

    Returns the view files that were created or refreshed (empty when the
    source is missing or unchanged).  Raises on unexpected I/O errors; callers
    treat view generation as best-effort.
    """

    job_root = Path(job_root)
    source = job_root / _PREPARED_SOURCE
    if source.is_symlink() or not source.is_file():
        return []

    view_dir = job_root / _VIEW_DIR
    manifest_path = view_dir / "components.json"
    structure_path = view_dir / "view.pdb"

    try:
        lines = source.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError):
        return []

    source_signature = _source_signature(source)
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("source_signature") == list(source_signature)
            and structure_path.is_file()
        ):
            return []

    polymer_atoms = 0
    water_atoms = 0
    ion_atoms = 0
    ligand_atoms = 0
    ligand_residues: dict[str, int] = {}
    ion_residues: dict[str, int] = {}
    water_residues = 0
    seen_residue_keys: set[tuple[str, str, str]] = set()
    box: dict[str, float] | None = None

    kept: list[str] = []
    header: list[str] = []
    truncated = False

    for line in lines:
        if line.startswith(("ATOM  ", "HETATM")):
            resname = _resname(line)
            chain = line[21:22]
            resseq = line[22:26].strip()
            residue_key = (chain, resseq, resname)
            is_new_residue = residue_key not in seen_residue_keys
            if is_new_residue:
                seen_residue_keys.add(residue_key)

            if line.startswith("ATOM  "):
                polymer_atoms += 1
                if len(kept) < max_view_atoms:
                    kept.append(line)
                else:
                    truncated = True
            elif resname in WATER_RESNAMES:
                water_atoms += 1
                if is_new_residue:
                    water_residues += 1
            elif resname in ION_RESNAMES:
                ion_atoms += 1
                if is_new_residue:
                    ion_residues[resname] = ion_residues.get(resname, 0) + 1
            else:
                ligand_atoms += 1
                if is_new_residue:
                    ligand_residues[resname] = ligand_residues.get(resname, 0) + 1
                if len(kept) < max_view_atoms:
                    kept.append(line)
                else:
                    truncated = True
        elif line.startswith("CRYST1"):
            box = _parse_box(line)
            header.append(line)
        elif line.startswith(("REMARK", "HEADER", "TITLE", "MODEL", "ENDMDL")):
            continue
        elif line.startswith(("TER", "END")):
            continue

    if not kept and polymer_atoms == 0 and ligand_atoms == 0:
        return []

    view_dir.mkdir(parents=True, exist_ok=True)
    note = (
        f"REMARK   1 DERIVED VIEW OF {_PREPARED_SOURCE.as_posix().upper()} "
        "FOR BROWSER DISPLAY"
    )
    atom_count_note = (
        f"REMARK   1 SOLVENT AND IONS REMOVED; "
        f"{polymer_atoms + ligand_atoms} SOLUTE ATOMS"
    )
    output = "\n".join([note, atom_count_note, *header, *kept, "END\n"])

    changed: list[Path] = []
    if not structure_path.is_file() or structure_path.read_text(
        encoding="utf-8"
    ) != output:
        structure_path.write_text(output, encoding="utf-8")
        changed.append(structure_path)

    manifest = {
        "group": "prepared",
        "source": _PREPARED_SOURCE.as_posix(),
        "source_signature": list(source_signature),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_atoms": polymer_atoms + water_atoms + ion_atoms + ligand_atoms,
        "view_atoms": polymer_atoms + ligand_atoms,
        "truncated": truncated,
        "polymer_atoms": polymer_atoms,
        "ligand_atoms": ligand_atoms,
        "water_atoms": water_atoms,
        "water_residues": water_residues,
        "ion_atoms": ion_atoms,
        "ions": [
            {"name": name, "count": count}
            for name, count in sorted(ion_residues.items())
        ],
        "ligands": [
            {"name": name, "residues": count}
            for name, count in sorted(ligand_residues.items())
        ],
        "box": box,
    }
    if _write_json_if_changed(manifest_path, manifest):
        changed.append(manifest_path)

    return changed


# ---------------------------------------------------------------------------
# Per-stage trajectory views (V3, mdtraj)
# ---------------------------------------------------------------------------


def _solute_atom_indices(topology: Any) -> list[int]:
    """Return atom indices for solute residues (non-water, non-ion)."""

    keep: list[int] = []
    for atom in topology.atoms:
        rname = atom.residue.name
        if rname not in WATER_RESNAMES and rname not in ION_RESNAMES:
            keep.append(atom.index)
    return keep


def _load_topology(path: Path) -> Any:
    """Parse the prepared-system topology.

    mdtraj builds a Python object per atom, so this is the expensive part of
    view generation.  It is done once per job and shared by every stage.
    """

    return md.load_topology(str(path))


def _frame_count(trajectory_path: Path, topology: Any) -> int:
    """Return the number of frames in a DCD without loading its coordinates.

    Reading a single atom per frame is enough to count the frames and costs
    almost nothing in memory.
    """

    probe = md.load(str(trajectory_path), top=topology, atom_indices=[0])
    return int(probe.n_frames)


def _stride_for_budget(
    n_frames: int,
    n_atoms: int,
    max_frames: int,
    max_dcd_mb: int,
) -> int:
    """Compute the smallest stride satisfying frame and byte budgets."""

    # DCD stores float32 x/y/z per atom per frame (~12 bytes/atom/frame),
    # plus a small per-frame header.  Use 16 bytes/atom/frame as a safe
    # overestimate so we never exceed the byte budget.
    bytes_per_frame = n_atoms * 16
    estimated_mb_per_frame = bytes_per_frame / (1024 * 1024)

    stride = 1
    while (
        n_frames // stride > max_frames
        or estimated_mb_per_frame * (n_frames / stride) > max_dcd_mb
    ):
        stride += 1
    return stride


def generate_stage_views(
    job_root: Path,
    stage_name: str,
    *,
    max_view_atoms: int = DEFAULT_MAX_VIEW_ATOMS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    max_dcd_mb: int = DEFAULT_MAX_DCD_MB,
    topology: Any = None,
) -> list[Path]:
    """Write ``outputs/views/<stage>/`` for a completed stage's trajectory.

    Returns the view files that were created or refreshed (empty when the
    source is missing, unchanged, or mdtraj is unavailable).  Trajectory
    derivation is best-effort and never fails a job.

    ``topology`` is the parsed prepared-system topology.  Pass it in when
    generating several stages so the (expensive) topology parse is not
    repeated for each one.
    """

    if not _MDTRAJ_AVAILABLE:
        return []

    job_root = Path(job_root)
    stage_dir = job_root / _STAGES_DIR / stage_name
    trajectory = stage_dir / "trajectory.dcd"
    topology_path = job_root / _PREPARED_SOURCE

    if not trajectory.is_file() or not topology_path.is_file():
        return []

    view_dir = job_root / "outputs" / "views" / stage_name
    view_pdb = view_dir / "view.pdb"
    view_dcd = view_dir / "view.dcd"
    frames_path = view_dir / "frames.json"
    final_pdb = view_dir / "final.pdb"

    source_signature = _source_signature(trajectory)
    if frames_path.is_file() and view_pdb.is_file() and view_dcd.is_file():
        try:
            existing = json.loads(frames_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("source_signature") == list(source_signature)
        ):
            return []

    if topology is None:
        try:
            topology = _load_topology(topology_path)
        except Exception as exc:  # mdtraj load failures are cosmetic
            return []

    n_atoms = int(topology.n_atoms)
    solute_indices = _solute_atom_indices(topology)
    if not solute_indices:
        return []

    try:
        n_frames = _frame_count(trajectory, topology)
        stride = _stride_for_budget(
            n_frames, len(solute_indices), max_frames, max_dcd_mb
        )
        # Read only the solute atoms and the frames we keep.  Loading the
        # whole trajectory first and slicing afterwards materializes every
        # atom of every frame and then copies the selection again.
        sliced = md.load(
            str(trajectory),
            top=topology,
            stride=stride,
            atom_indices=solute_indices,
        )
    except Exception as exc:  # mdtraj load failures are cosmetic
        return []

    if sliced.n_frames == 0 or sliced.n_atoms == 0:
        return []

    kept_frames = sliced.n_frames

    view_dir.mkdir(parents=True, exist_ok=True)

    # view.pdb: topology from the first frame of the sliced trajectory.
    changed: list[Path] = []
    tmp_pdb = view_dir / "view.pdb.tmp"
    sliced[0].save_pdb(str(tmp_pdb))
    pdb_text = tmp_pdb.read_text(encoding="utf-8")
    tmp_pdb.unlink()
    if not view_pdb.is_file() or view_pdb.read_text(encoding="utf-8") != pdb_text:
        view_pdb.write_text(pdb_text, encoding="utf-8")
        changed.append(view_pdb)

    # view.dcd: binary trajectory of the sliced frames.
    try:
        existing_dcd = view_dcd.read_bytes() if view_dcd.is_file() else None
    except OSError:
        existing_dcd = None
    tmp_dcd = view_dir / "view.dcd.tmp"
    sliced.save_dcd(str(tmp_dcd))
    dcd_bytes = tmp_dcd.read_bytes()
    tmp_dcd.unlink()
    if existing_dcd != dcd_bytes:
        view_dcd.write_bytes(dcd_bytes)
        changed.append(view_dcd)

    # final.pdb: snapshot of the last frame.
    tmp_final = view_dir / "final.pdb.tmp"
    sliced[-1].save_pdb(str(tmp_final))
    final_pdb_text = tmp_final.read_text(encoding="utf-8")
    tmp_final.unlink()
    if not final_pdb.is_file() or final_pdb.read_text(encoding="utf-8") != final_pdb_text:
        final_pdb.write_text(final_pdb_text, encoding="utf-8")
        changed.append(final_pdb)

    try:
        dt_ps = float(sliced.timestep)
    except (TypeError, ValueError):
        dt_ps = None

    manifest = {
        "group": stage_name,
        "source": f"outputs/stages/{stage_name}/trajectory.dcd",
        "topology": _PREPARED_SOURCE.as_posix(),
        "source_signature": list(source_signature),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_frames": n_frames,
        "source_atoms": n_atoms,
        "view_frames": kept_frames,
        "view_atoms": len(solute_indices),
        "stride": stride,
        "dt_ps": dt_ps,
        "truncated": stride > 1,
    }
    if _write_json_if_changed(frames_path, manifest):
        changed.append(frames_path)

    return changed


# ---------------------------------------------------------------------------
# Time series from simulation.log (V3, stdlib CSV parsing)
# ---------------------------------------------------------------------------

_SERIES_NUMERIC_COLUMNS = (
    "Potential Energy (kJ/mole)",
    "Kinetic Energy (kJ/mole)",
    "Temperature (K)",
    "Density (g/mL)",
    "Box Volume (nm^3)",
    "Speed (ns/day)",
)


def _parse_simulation_log(path: Path) -> list[dict[str, Any]]:
    """Parse an OpenMM StateDataReporter simulation.log into point dicts."""

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Find the header line: first non-empty line starting with '#'.
    header_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            header_index = i
            break
    if header_index is None:
        return []

    # Strip the leading '#' and parse the CSV header.
    header_line = lines[header_index]
    if header_line.lstrip().startswith("#"):
        header_line = header_line.lstrip("#").strip()
    reader = csv.reader([header_line])
    try:
        columns = next(reader)
    except StopIteration:
        return []
    columns = [c.strip().strip('"') for c in columns]

    points: list[dict[str, Any]] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        row = next(csv.reader([stripped]))
        if len(row) != len(columns):
            continue
        point: dict[str, Any] = {}
        for col, val in zip(columns, row):
            col = col.strip().strip('"')
            val = val.strip().strip('"')
            # Try numeric parse.
            try:
                if "." in val or "e" in val.lower():
                    point[col] = float(val)
                else:
                    point[col] = int(val)
            except ValueError:
                point[col] = val
        points.append(point)

    return points


def _downsample_series(
    points: list[dict[str, Any]],
    max_points: int,
) -> list[dict[str, Any]]:
    """Downsample *points* to at most *max_points*, preserving min/max.

    Strategy: stride-decimate to roughly *max_points* points, then force in
    the first, last, and min/max points of each numeric column so extrema are
    never lost.  Results are re-sorted by step.
    """

    if len(points) <= max_points:
        return points

    stride = math.ceil(len(points) / max_points)
    sampled = points[::stride]

    # Force-include first, last, and column extrema (these must survive
    # trimming).
    must_keep: dict[Any, dict[str, Any]] = {}
    for p in [points[0], points[-1]]:
        must_keep[p.get("Step")] = p
    for col in _SERIES_NUMERIC_COLUMNS:
        numeric_points = [
            p
            for p in points
            if isinstance(p.get(col), (int, float))
        ]
        if not numeric_points:
            continue
        for extreme in (min(numeric_points, key=lambda p: p[col]),
                        max(numeric_points, key=lambda p: p[col])):
            must_keep[extreme.get("Step")] = extreme

    # De-duplicate sampled points by step.
    seen_steps: set[Any] = set()
    combined: list[dict[str, Any]] = []
    for p in sampled:
        step = p.get("Step")
        if step in seen_steps:
            continue
        seen_steps.add(step)
        combined.append(p)

    # Append any must-keep points not already present.
    for step, p in must_keep.items():
        if step not in seen_steps:
            combined.append(p)
            seen_steps.add(step)

    combined.sort(key=lambda p: p.get("Step", 0))

    if len(combined) > max_points:
        # Always keep must-keep points; thin the stride samples from the
        # middle to fit within max_points.
        must_steps = set(must_keep.keys())
        optional = [p for p in combined if p.get("Step") not in must_steps]
        keep_optional = max_points - len(must_steps)
        if keep_optional > 0 and len(optional) > keep_optional:
            indices = [
                int(round(i * (len(optional) - 1) / (keep_optional - 1)))
                if keep_optional > 1 else 0
                for i in range(keep_optional)
            ]
            optional = [optional[i] for i in sorted(set(indices))]
        combined = sorted(
            [must_keep[s] for s in sorted(must_steps)] + optional,
            key=lambda p: p.get("Step", 0),
        )

    return combined


def generate_series(
    job_root: Path,
    stage_name: str,
    *,
    max_points: int = DEFAULT_MAX_SERIES_POINTS,
) -> list[Path]:
    """Write ``outputs/analysis/series.json`` for a completed stage's state log.

    Returns the series file that was created or refreshed (empty when the
    source is missing or unchanged).  Series derivation is best-effort and
    never fails a job.
    """

    job_root = Path(job_root)
    stage_dir = job_root / _STAGES_DIR / stage_name
    log_path = stage_dir / "simulation.log"

    if not log_path.is_file():
        return []

    series_dir = job_root / _ANALYSIS_DIR
    series_path = series_dir / "series.json"

    source_signature = _source_signature(log_path)
    if series_path.is_file():
        try:
            existing = json.loads(series_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        if (
            isinstance(existing, dict)
            and existing.get("source_signature") == list(source_signature)
        ):
            return []

    points = _parse_simulation_log(log_path)
    if not points:
        return []

    downsampled = _downsample_series(points, max_points)

    # Determine column order from the first point.
    columns = list(points[0].keys())

    manifest = {
        "group": stage_name,
        "source": f"outputs/stages/{stage_name}/simulation.log",
        "source_signature": list(source_signature),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_points": len(points),
        "view_points": len(downsampled),
        "columns": columns,
        "points": downsampled,
    }
    if _write_json_if_changed(series_path, manifest):
        return [series_path]
    return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _completed_stages_with_trajectory(job_root: Path) -> list[str]:
    """Return stage directory names under outputs/stages/ that have a
    trajectory.dcd and a completed stage.json."""

    stages_root = job_root / _STAGES_DIR
    if not stages_root.is_dir():
        return []

    completed: list[str] = []
    for child in sorted(stages_root.iterdir()):
        if not child.is_dir():
            continue
        trajectory = child / "trajectory.dcd"
        manifest = child / "stage.json"
        if not trajectory.is_file() or not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("status") == "completed":
            completed.append(child.name)
    return completed


def generate_views(job_root: Path) -> list[Path]:
    """Entry point used by the worker after a run finishes.

    Generates every currently supported view; each derivation is
    independent, and failures of one do not affect the others.
    """

    job_root = Path(job_root)
    created: list[Path] = []
    created.extend(generate_prepared_view(job_root))

    stages = _completed_stages_with_trajectory(job_root)
    if not stages:
        return created

    # The prepared-system topology is the same for every stage and parsing
    # it is the slowest part of view generation, so it is parsed once here
    # and shared by all stages.
    topology = None
    topology_path = job_root / _PREPARED_SOURCE
    if _MDTRAJ_AVAILABLE and topology_path.is_file():
        try:
            topology = _load_topology(topology_path)
        except Exception:  # pragma: no cover - defensive
            topology = None

    for stage_name in stages:
        try:
            created.extend(
                generate_stage_views(job_root, stage_name, topology=topology)
            )
        except Exception as exc:  # pragma: no cover - defensive
            # One stage's view failure must not affect other stages.
            pass
        try:
            created.extend(generate_series(job_root, stage_name))
        except Exception as exc:  # pragma: no cover - defensive
            pass

    return created
