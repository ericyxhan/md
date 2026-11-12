"""Tests for prep_ops structure operations (remove_residues, keep_selection)."""

from __future__ import annotations

from pathlib import Path

from prep_ops import keep_selection, remove_residues

PDB_CONTENT = (
    "CRYST1   50.000   50.000   50.000  90.00  90.00  90.00 P 1\n"
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
    "ATOM      2  CA  ALA A   1       2.000   3.000   4.000  1.00 20.00           C\n"
    "ATOM      3  C   ALA A   1       3.000   4.000   5.000  1.00 20.00           C\n"
    "ATOM      4  N   GLY A   2       4.000   5.000   6.000  1.00 20.00           N\n"
    "ATOM      5  CA  GLY A   2       5.000   6.000   7.000  1.00 20.00           C\n"
    "ATOM      6  N   VAL A   3       6.000   7.000   8.000  1.00 20.00           N\n"
    "ATOM      7  N   ALA B   1       9.000  10.000  11.000  1.00 20.00           N\n"
    "ATOM      8  CA  ALA B   1      10.000  11.000  12.000  1.00 20.00           C\n"
    "END\n"
)


def _count_atoms(pdb_path: Path) -> int:
    return sum(
        1
        for line in pdb_path.read_text().splitlines()
        if line.startswith(("ATOM  ", "HETATM"))
    )


def _residues(pdb_path: Path) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for line in pdb_path.read_text().splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            chain = line[21:22].strip()
            resname = line[17:20].strip()
            resseq = int(line[22:26].strip())
            found.append((chain, resname, resseq))
    return found


def test_remove_residues_removes_specified_residues(tmp_path: Path) -> None:
    source = tmp_path / "input.pdb"
    source.write_text(PDB_CONTENT)
    output = tmp_path / "output.pdb"

    remove_residues(
        source,
        [{"chain": "A", "resnum": 2, "icode": " "}],
        output,
    )

    atoms = _count_atoms(output)
    # ALA A/1 (3) + VAL A/3 (1) + ALA B/1 (2) = 6 atoms remain (GLY A/2 removed)
    assert atoms == 6
    resis = _residues(output)
    assert ("A", "GLY", 2) not in resis
    assert ("A", "ALA", 1) in resis
    assert ("A", "VAL", 3) in resis
    assert ("B", "ALA", 1) in resis


def test_remove_residues_removes_multiple(tmp_path: Path) -> None:
    source = tmp_path / "input.pdb"
    source.write_text(PDB_CONTENT)
    output = tmp_path / "output.pdb"

    remove_residues(
        source,
        [
            {"chain": "A", "resnum": 1, "icode": " "},
            {"chain": "B", "resnum": 1, "icode": " "},
        ],
        output,
    )

    atoms = _count_atoms(output)
    # Only GLY A/2 (2 atoms) + VAL A/3 (1 atom) remain
    assert atoms == 3


def test_keep_selection_keeps_only_specified(tmp_path: Path) -> None:
    source = tmp_path / "input.pdb"
    source.write_text(PDB_CONTENT)
    output = tmp_path / "output.pdb"

    keep_selection(
        source,
        [{"chain": "A", "resnum": 1, "icode": " "}],
        output,
    )

    atoms = _count_atoms(output)
    assert atoms == 3  # only ALA A/1
    resis = set(_residues(output))
    assert resis == {("A", "ALA", 1)}


def test_keep_selection_with_icode(tmp_path: Path) -> None:
    content = PDB_CONTENT.replace("ALA A   1", "ALA A   1A")
    source = tmp_path / "input.pdb"
    source.write_text(content)
    output = tmp_path / "output.pdb"

    keep_selection(
        source,
        [{"chain": "A", "resnum": 1, "icode": "A"}],
        output,
    )

    atoms = _count_atoms(output)
    assert atoms == 3  # only ALA A/1 with icode A


def test_remove_residues_empty_specs_keeps_all(tmp_path: Path) -> None:
    source = tmp_path / "input.pdb"
    source.write_text(PDB_CONTENT)
    output = tmp_path / "output.pdb"

    remove_residues(source, [], output)

    assert _count_atoms(output) == _count_atoms(source)
