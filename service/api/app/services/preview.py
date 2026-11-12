"""Browser-sized previews of large structure files.

A prepared or membrane-embedded system is a solvated box: hundreds of
thousands of atoms, the large majority of them water and ions.  Sending
those bytes to a browser is slow and useless for orientation, and a file
above the preview size limit cannot be served raw at all.

This module derives a *preview* of such a file: the solvent and ions are
removed and the solute (protein, lipids, ligands) is kept.  The result is
cached next to the upload and rebuilt when the source changes.

The derivation is best effort.  If the file cannot be parsed, the caller
falls back to reporting that the file is too large to preview.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

# Residue names treated as solvent.
WATER_RESNAMES = frozenset(
    {"HOH", "WAT", "H2O", "OH2", "D3O", "DOD", "TIP", "TIP3", "TIP4", "SOL"}
)

# Residue names treated as ions.
ION_RESNAMES = frozenset(
    {
        "NA", "CL", "K", "CA", "MG", "ZN", "FE", "FE2", "CU", "CU1", "MN",
        "MN3", "CO", "NI", "BR", "I", "IOD", "F", "LI", "RB", "CS", "NA+",
        "CL-", "K+", "SOD", "POT", "CAL", "CLA",
    }
)

_SOLVENT = WATER_RESNAMES | ION_RESNAMES


def source_signature(path: Path) -> list[int]:
    """Return a cheap signature that changes when the source changes."""

    stat = path.stat()
    return [stat.st_size, int(stat.st_mtime)]


def _manifest_path(preview: Path) -> Path:
    return preview.with_name(preview.stem + ".json")


def _is_solvent(residue: Any) -> bool:
    return residue.name.strip().upper() in _SOLVENT


def _atom_bounds(structure: Any) -> tuple[float, float, float] | None:
    """Return the ``(a, b, c)`` extent of the atoms, in Angstrom."""

    minimum = [math.inf, math.inf, math.inf]
    maximum = [-math.inf, -math.inf, -math.inf]
    found = False
    for model in structure:
        for chain in model:
            for residue in chain:
                for atom in residue:
                    position = atom.pos
                    found = True
                    for axis in range(3):
                        value = (position.x, position.y, position.z)[axis]
                        if value < minimum[axis]:
                            minimum[axis] = value
                        if value > maximum[axis]:
                            maximum[axis] = value
    if not found:
        return None
    return (
        max(1.0, maximum[0] - minimum[0]),
        max(1.0, maximum[1] - minimum[1]),
        max(1.0, maximum[2] - minimum[2]),
    )


def _has_real_cell(structure: Any) -> bool:
    """Whether the source declared a unit cell.

    A structure without a CRYST1 record gets the 1x1x1 default from gemmi,
    which is not a usable box.
    """

    cell = structure.cell
    return not (
        abs(cell.a - 1.0) < 1e-6
        and abs(cell.b - 1.0) < 1e-6
        and abs(cell.c - 1.0) < 1e-6
    )


def _build(source: Path, destination: Path, max_atoms: int) -> dict[str, Any]:
    """Write a solute-focused copy of *source* to *destination*."""

    import gemmi

    structure = gemmi.read_structure(str(source))

    reduced = gemmi.Structure()
    reduced.name = structure.name
    reduced.spacegroup_hm = structure.spacegroup_hm

    kept = 0
    removed = 0
    truncated = False

    for model in structure:
        new_model = gemmi.Model(model.num)
        for chain in model:
            new_chain = gemmi.Chain(chain.name)
            for residue in chain:
                if _is_solvent(residue):
                    removed += len(residue)
                    continue
                if kept + len(residue) > max_atoms:
                    truncated = True
                    removed += len(residue)
                    continue
                new_chain.add_residue(residue)
                kept += len(residue)
            if len(new_chain):
                new_model.add_chain(new_chain)
        reduced.add_model(new_model)

    if kept == 0:
        raise ValueError("structure contains only solvent")

    # Packmol output has no CRYST1 record, so gemmi would write the 1x1x1
    # default cell.  A box that small makes the viewer render a nonsense
    # unit cell, so derive the real extent from the coordinates instead.
    if _has_real_cell(structure):
        reduced.cell = structure.cell
    else:
        bounds = _atom_bounds(reduced)
        if bounds is not None:
            reduced.cell = gemmi.UnitCell(bounds[0], bounds[1], bounds[2], 90, 90, 90)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(reduced.make_pdb_string(), encoding="utf-8")
    temporary.replace(destination)

    return {
        "source_signature": source_signature(source),
        "atoms": kept,
        "removed_atoms": removed,
        "truncated": truncated,
    }


def ensure_preview(
    source: Path,
    preview: Path,
    *,
    max_atoms: int,
) -> Path | None:
    """Return a browser-sized preview of *source*, building it if needed.

    Returns ``None`` when the file cannot be parsed into a structure with
    something left to show.
    """

    if preview.is_file():
        manifest_path = _manifest_path(preview)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None
        if (
            isinstance(manifest, dict)
            and manifest.get("source_signature") == source_signature(source)
        ):
            return preview

    try:
        manifest = _build(source, preview, max_atoms)
    except Exception:
        # A file that cannot be parsed as a structure has no preview.
        return None

    try:
        _manifest_path(preview).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return preview
