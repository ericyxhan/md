"""The atom budget on uploaded structures.

A byte limit does not bound the cost of a simulation: the GPU time grows with
the number of atoms.  The upload therefore counts the atoms and rejects a
structure that is over the limit, before it can reach the queue.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.structure import count_atoms

PDB_WITH_ATOMS = """HEADER    TEST
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.500   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.000   1.400   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       3.400   1.500   0.000  1.00  0.00           O
END
"""

SDF_WITH_ATOMS = """test
  RDKit          3D

  2  1  0  0  0  0  0  0  0  0999 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  1  2  1  0
M  END
"""


def test_counts_atoms_in_a_pdb(tmp_path: Path) -> None:
    path = tmp_path / "a.pdb"
    path.write_text(PDB_WITH_ATOMS)
    assert count_atoms(path, ".pdb") == 4


def test_counts_atoms_in_an_sdf(tmp_path: Path) -> None:
    path = tmp_path / "a.sdf"
    path.write_text(SDF_WITH_ATOMS)
    assert count_atoms(path, ".sdf") == 2


def test_counts_atoms_in_a_mol2(tmp_path: Path) -> None:
    path = tmp_path / "a.mol2"
    path.write_text(
        "@<TRIPOS>MOLECULE\n"
        "name\n"
        " 3 2 1 0 0\n"
        "@<TRIPOS>ATOM\n"
        "      3    1    0    0    0\n"
        "      C1     0.0000   0.0000   0.0000 C.3    1  LIG1\n"
        "      C2     1.5000   0.0000   0.0000 C.3    1  LIG1\n"
        "      C3     2.0000   1.4000   0.0000 C.3    1  LIG1\n"
    )
    assert count_atoms(path, ".mol2") == 3


def test_unreadable_file_has_no_count(tmp_path: Path) -> None:
    path = tmp_path / "a.pdb"
    path.write_text("this is not a structure\n")
    assert count_atoms(path, ".pdb") is None


def test_upload_over_the_atom_limit_is_rejected(client, auth, settings) -> None:
    settings.max_upload_atoms = 2
    response = client.post(
        "/api/v1/files",
        headers=auth,
        files={
            "file": (
                "complex.pdb",
                PDB_WITH_ATOMS.encode(),
                "chemical/x-pdb",
            )
        },
    )
    assert response.status_code == 413, response.text
    body = response.json()
    assert body["error"]["code"] == "too_many_atoms"
    assert body["error"]["details"]["atoms"] == 4
    assert body["error"]["details"]["limit"] == 2


def test_upload_within_the_atom_limit_is_accepted(client, auth) -> None:
    response = client.post(
        "/api/v1/files",
        headers=auth,
        files={
            "file": (
                "complex.pdb",
                PDB_WITH_ATOMS.encode(),
                "chemical/x-pdb",
            )
        },
    )
    assert response.status_code == 201, response.text


def test_rejected_upload_leaves_no_file_behind(
    client, auth, settings, app
) -> None:
    settings.max_upload_atoms = 1
    client.post(
        "/api/v1/files",
        headers=auth,
        files={
            "file": (
                "complex.pdb",
                PDB_WITH_ATOMS.encode(),
                "chemical/x-pdb",
            )
        },
    )
    uploads = app.state.storage.uploads
    assert not any(uploads.iterdir()), "the rejected upload was not removed"
