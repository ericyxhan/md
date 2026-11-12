"""Cheap structural checks on uploaded files.

Counting the atoms in an uploaded structure is bounded and cheap: gemmi
parses a PDB or mmCIF file in milliseconds, and the ligand formats carry
their own count.  Knowing the atom count before a job is queued rejects a
file that would otherwise burn hours of GPU time, and it turns a failure
minutes into a failure seconds after the upload.

The count is advisory when the format cannot be read: an unreadable file is
allowed through, because the parameterizer reports the real problem with a
better message than this check could.
"""

from __future__ import annotations

from pathlib import Path

# The ligand formats are not gemmi's business, and both carry an atom count.
_SDF_SUFFIXES = frozenset({".sdf", ".mol", ".mol2"})


def count_atoms(path: Path, suffix: str) -> int | None:
    """Return the number of atoms in a structure file.

    ``None`` means the format is not countable here, or the file could not
    be read; the caller should allow the upload in that case.
    """

    suffix = suffix.lower()
    if suffix in _SDF_SUFFIXES:
        return _count_ligand_atoms(path)
    return _count_gemmi_atoms(path)


def _count_gemmi_atoms(path: Path) -> int | None:
    try:
        import gemmi
    except ImportError:  # pragma: no cover - gemmi is a hard dependency
        return None

    try:
        structure = gemmi.read_structure(str(path))
    except Exception:
        return None

    total = 0
    for model in structure:
        for chain in model:
            for residue in chain:
                total += len(residue)
    # An empty parse is more likely a file that is not a structure than a
    # structure with no atoms, so it counts as "cannot be counted" rather
    # than as a confident zero.
    return total or None


def _count_ligand_atoms(path: Path) -> int | None:
    """Read the atom count from an SDF or MOL2 file.

    Both formats record the count in a fixed place: an SDF has it on the
    counts line of its connection table, and a MOL2 has it on the header
    line of its atom section.
    """

    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None

    if path.suffix.lower() == ".mol2":
        return _count_mol2_atoms(text)
    return _count_sdf_atoms(text)


def _count_sdf_atoms(text: str) -> int | None:
    lines = text.splitlines()
    # An SDF connection table is a fixed four-line header followed by the
    # counts line, which carries the atom count in its first field.
    for index, line in enumerate(lines[:40]):
        if "V3000" in line:
            # A V3000 connection table records the counts further down.
            for follow in lines[index + 1 : index + 40]:
                if "COUNTS" in follow:
                    parts = follow.split()
                    if len(parts) >= 3:
                        try:
                            return int(parts[-3])
                        except ValueError:
                            return None
            return None
        if "V2000" in line:
            parts = line.split()
            if parts:
                try:
                    return int(parts[0])
                except ValueError:
                    return None
    return None


def _count_mol2_atoms(text: str) -> int | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("@<TRIPOS>ATOM"):
            continue
        # The atom count is on the line after the section header, but some
        # writers put a blank line in between, so a few are tried.
        for follow in lines[index + 1 : index + 4]:
            parts = follow.split()
            if len(parts) >= 2:
                try:
                    return int(parts[0])
                except ValueError:
                    continue
        return None
    return None
