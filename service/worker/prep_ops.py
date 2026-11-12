"""System-preparation operations: ligand removal, chain selection, ligand addition.

These operate on PDB files using gemmi (structure manipulation) and a minimal
SDF parser (ligand input).  They are CPU-only and run inside the prep worker
process (no subprocess needed for these ops).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gemmi


# ---------------------------------------------------------------------------
# Minimal SDF parser (no RDKit dependency)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LigandAtom:
    name: str
    element: str
    x: float
    y: float
    z: float
    charge: float = 0.0


def parse_sdf(path: Path) -> list[LigandAtom]:
    """Parse an SDF/MOL file and return a list of LigandAtom.

    This is a minimal parser sufficient for the atom block of a typical
    small-molecule SDF.  It does not handle bonds, stereochemistry, or
    complex V3000 blocks — for those, supply a PDB ligand instead.
    """

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Find the atom/bond counts line (line 4 in V2000).
    counts_line_index = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and stripped[0].isdigit():
            parts = stripped.split()
            if len(parts) >= 2:
                try:
                    natoms = int(parts[0])
                    nbonds = int(parts[1])
                    counts_line_index = i
                    break
                except ValueError:
                    continue
    if counts_line_index is None:
        raise ValueError(f"Could not parse SDF counts line in {path}")

    # V2000 atom block starts right after the counts line.
    atom_start = counts_line_index + 1
    atoms: list[LigandAtom] = []
    for i in range(atom_start, atom_start + natoms):
        if i >= len(lines):
            break
        line = lines[i]
        # V2000 atom line: x(10.4) y(10.4) z(10.4) atom_symbol(3-4) ...
        try:
            x = float(line[0:10])
            y = float(line[10:20])
            z = float(line[20:30])
            symbol = line[31:34].strip()
        except (ValueError, IndexError):
            continue
        charge = 0.0
        if len(line) > 159:
            try:
                md = int(line[155:159].strip() or "0")
                charge = float(md)
            except ValueError:
                pass
        atoms.append(
            LigandAtom(
                name=symbol,
                element=symbol,
                x=x,
                y=y,
                z=z,
                charge=charge,
            )
        )
    return atoms


# ---------------------------------------------------------------------------
# Structure operations using gemmi
# ---------------------------------------------------------------------------


def _filter_chain_residues(
    chain: gemmi.Chain, keep_names: set[str]
) -> list[gemmi.Residue]:
    """Return cloned residues from *chain* whose names are in *keep_names*."""
    kept: list[gemmi.Residue] = []
    for residue in chain:
        if residue.name in keep_names:
            kept.append(residue.clone())
    return kept


def _replace_chain_residues(
    model: gemmi.Model,
    chain_name: str,
    kept_residues: list[gemmi.Residue],
) -> None:
    """Replace *chain_name* in *model* with a new chain containing *kept_residues*."""
    model.remove_chain(chain_name)
    new_chain = gemmi.Chain(chain_name)
    for residue in kept_residues:
        new_chain.add_residue(residue)
    model.add_chain(new_chain)


def remove_ligand(
    pdb_path: Path,
    ligand_resname: str,
    output_path: Path,
) -> Path:
    """Remove all residues with the given residue name from a PDB.

    Returns the output path.
    """

    structure = gemmi.read_structure(str(pdb_path))
    target = ligand_resname.upper()
    for model in structure:
        for chain in model:
            kept = [
                residue.clone()
                for residue in chain
                if residue.name.upper() != target
            ]
            _replace_chain_residues(model, chain.name, kept)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(output_path))
    return output_path


def select_chain(
    pdb_path: Path,
    chain_ids: list[str],
    output_path: Path,
) -> Path:
    """Keep only the specified chain IDs from a PDB.

    Returns the output path.
    """

    structure = gemmi.read_structure(str(pdb_path))
    keep = set(chain_ids)
    for model in structure:
        chains_to_remove = [
            chain.name for chain in model if chain.name not in keep
        ]
        for chain_name in chains_to_remove:
            model.remove_chain(chain_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(output_path))
    return output_path


def add_ligand(
    pdb_path: Path,
    ligand_paths: list[Path],
    output_path: Path,
) -> Path:
    """Add one or more ligand molecules (SDF/MOL or PDB) to a PDB structure.

    Ligands are appended to chain "Z" with unique residue numbers.
    Returns the output path.
    """

    structure = gemmi.read_structure(str(pdb_path))

    # Find the next available residue number.
    max_resnum = 0
    for model in structure:
        for chain in model:
            for residue in chain:
                try:
                    num = int(residue.seqid.num)
                    if num > max_resnum:
                        max_resnum = num
                except ValueError:
                    continue

    model = structure[0]
    # Use chain "Z" for ligands (create if not exists).
    chain_names = [chain.name for chain in model]
    if "Z" in chain_names:
        chain = model["Z"]
    else:
        chain = model.add_chain(gemmi.Chain("Z"))

    resnum = max_resnum + 1
    for ligand_path in ligand_paths:
        suffix = ligand_path.suffix.lower()
        if suffix in {".pdb", ".ent"}:
            lig_struct = gemmi.read_structure(str(ligand_path))
            for lig_model in lig_struct:
                for lig_chain in lig_model:
                    for residue in lig_chain:
                        new_res = gemmi.Residue()
                        new_res.name = residue.name[:3].upper() or "LIG"
                        new_res.seqid = gemmi.SeqId(str(resnum), " ")
                        for atom in residue:
                            new_atom = gemmi.Atom()
                            new_atom.name = atom.name[:4]
                            new_atom.pos = atom.pos
                            new_atom.element = gemmi.Element(atom.element)
                            new_atom.occ = atom.occ
                            new_atom.b_iso = atom.b_iso
                            new_res.add_atom(new_atom)
                        chain.add_residue(new_res)
                        resnum += 1
        elif suffix in {".sdf", ".mol"}:
            atoms = parse_sdf(ligand_path)
            resname = ligand_path.stem.upper()[:3] or "LIG"
            for atom in atoms:
                new_res = gemmi.Residue()
                new_res.name = resname
                new_res.seqid = gemmi.SeqId(str(resnum), " ")
                new_atom = gemmi.Atom()
                new_atom.name = atom.name[:4]
                new_atom.pos = gemmi.Position(atom.x, atom.y, atom.z)
                new_atom.element = gemmi.Element(atom.element)
                new_atom.occ = 1.0
                new_atom.b_iso = 0.0
                new_res.add_atom(new_atom)
                chain.add_residue(new_res)
            resnum += 1
        else:
            raise ValueError(
                f"Unsupported ligand format {suffix!r}; use PDB or SDF/MOL"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(output_path))
    return output_path


def inspect_pdb(pdb_path: Path) -> dict[str, Any]:
    """Inspect a PDB file and return chains, residues, and ligands.

    Used by the frontend to populate chain/ligand pickers.
    """

    structure = gemmi.read_structure(str(pdb_path))
    chains: dict[str, list[str]] = {}
    ligands: list[str] = []

    for model in structure:
        for chain in model:
            cid = chain.name
            if cid not in chains:
                chains[cid] = []
            for residue in chain:
                rname = residue.name.strip()
                chains[cid].append(rname)
                if _is_likely_ligand(rname):
                    if rname not in ligands:
                        ligands.append(rname)

    return {
        "chains": {cid: sorted(set(resnames)) for cid, resnames in chains.items()},
        "ligands": sorted(ligands),
    }


_STANDARD_RESNAMES = frozenset(
    {
        "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
        "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
        "HOH", "WAT", "O", "OH2",
        "NA", "CL", "K", "CA", "MG", "ZN", "FE", "CU", "MN", "CO", "NI",
    }
)


def _is_likely_ligand(resname: str) -> bool:
    """Heuristic: a residue is likely a ligand if it's not a standard
    amino acid, water, or common ion."""
    upper = resname.upper().strip()
    if upper in _STANDARD_RESNAMES:
        return False
    if len(upper) <= 2 and upper.isalpha():
        return False
    return True


# ---------------------------------------------------------------------------
# Explicit residue selection (click/drag-driven editing)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResidueSpec:
    """A residue identified by chain, sequence number, and insertion code."""

    chain: str
    resnum: int
    icode: str = " "


def _parse_residue_specs(specs: list[dict[str, Any]]) -> set[ResidueSpec]:
    """Parse a list of {chain, resnum, icode} dicts into ResidueSpecs."""
    parsed: set[ResidueSpec] = set()
    for spec in specs:
        chain = str(spec["chain"])
        resnum = int(spec["resnum"])
        icode = str(spec.get("icode", " "))
        parsed.add(ResidueSpec(chain=chain, resnum=resnum, icode=icode))
    return parsed


def _match_residue(chain_name: str, residue: gemmi.Residue, specs: set[ResidueSpec]) -> bool:
    """Return True when *residue* matches one of *specs*."""
    return ResidueSpec(
        chain=chain_name,
        resnum=int(residue.seqid.num),
        icode=residue.seqid.icode,
    ) in specs


def remove_residues(
    pdb_path: Path,
    residue_specs: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    """Remove the explicitly listed residues from a PDB.

    *residue_specs* is a list of ``{"chain": str, "resnum": int, "icode": str}``
    dicts.  Returns the output path.
    """

    specs = _parse_residue_specs(residue_specs)
    structure = gemmi.read_structure(str(pdb_path))
    for model in structure:
        # Collect chain names first so we don't mutate the model while
        # iterating over it (remove_chain/add_chain corrupts the iterator).
        chain_names = [chain.name for chain in model]
        for chain_name in chain_names:
            chain = model[chain_name]
            kept = [
                residue.clone()
                for residue in chain
                if not _match_residue(chain_name, residue, specs)
            ]
            _replace_chain_residues(model, chain_name, kept)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(output_path))
    return output_path


def keep_selection(
    pdb_path: Path,
    residue_specs: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    """Keep only the explicitly listed residues, removing everything else.

    *residue_specs* is a list of ``{"chain": str, "resnum": int, "icode": str}``
    dicts.  Returns the output path.
    """

    specs = _parse_residue_specs(residue_specs)
    structure = gemmi.read_structure(str(pdb_path))
    for model in structure:
        chain_names = [chain.name for chain in model]
        for chain_name in chain_names:
            chain = model[chain_name]
            kept = [
                residue.clone()
                for residue in chain
                if _match_residue(chain_name, residue, specs)
            ]
            _replace_chain_residues(model, chain_name, kept)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    structure.write_pdb(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# Detailed structure inspection (for the /files/{id}/inspect endpoint)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainInfo:
    chain_id: str
    residue_names: list[str]
    residue_count: int
    atom_count: int


def inspect_structure(pdb_path: Path) -> dict[str, Any]:
    """Inspect a PDB file and return a detailed summary for the viewer UI.

    Returns chains, residue ranges, components (protein / water / ion / ligand
    atom counts), total atom count, model count, and a bounding box.
    """

    structure = gemmi.read_structure(str(pdb_path))
    chains: dict[str, ChainInfo] = {}
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
                chains[cid] = ChainInfo(
                    chain_id=cid,
                    residue_names=[],
                    residue_count=0,
                    atom_count=0,
                )
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
                        min_pos = gemmi.Position(pos.x, pos.y, pos.z)
                        max_pos = gemmi.Position(pos.x, pos.y, pos.z)
                    else:
                        min_pos.x = min(min_pos.x, pos.x)
                        min_pos.y = min(min_pos.y, pos.y)
                        min_pos.z = min(min_pos.z, pos.z)
                        max_pos.x = max(max_pos.x, pos.x)
                        max_pos.y = max(max_pos.y, pos.y)
                        max_pos.z = max(max_pos.z, pos.z)

                if _is_likely_ligand(rname):
                    ligand_atoms += res_atoms
                elif rname in {"HOH", "WAT", "O", "OH2"}:
                    water_atoms += res_atoms
                elif rname in {"NA", "CL", "K", "CA", "MG", "ZN", "FE", "CU", "MN", "CO", "NI"}:
                    ion_atoms += res_atoms
                else:
                    protein_atoms += res_atoms

            # Rebuild ChainInfo with final counts (dataclass is frozen).
            chains[cid] = ChainInfo(
                chain_id=cid,
                residue_names=sorted(set(residue_names)),
                residue_count=residue_count,
                atom_count=chain_atom_count,
            )

    bounding_box = None
    if min_pos is not None and max_pos is not None:
        bounding_box = {
            "min": {"x": min_pos.x, "y": min_pos.y, "z": min_pos.z},
            "max": {"x": max_pos.x, "y": max_pos.y, "z": max_pos.z},
        }

    return {
        "chains": {
            cid: {
                "residues": info.residue_names,
                "residue_count": info.residue_count,
                "atom_count": info.atom_count,
            }
            for cid, info in chains.items()
        },
        "ligands": sorted(
            {
                rname
                for info in chains.values()
                for rname in info.residue_names
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
