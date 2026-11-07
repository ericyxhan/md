#!/usr/bin/env python3
"""Build a combined OpenMM System for a protein plus its ligands.

This script runs in the parameterization environment (OpenFF Toolkit, RDKit,
PDBFixer, gemmi, and OpenMM).  It is intentionally separate from
``simulate.py`` so the simulation environment only needs OpenMM/CUDA and can
load the resulting ``system.xml`` and ``prepared.pdb``.

Two input modes are supported:

* ``--complex structure.pdb``
  A single file containing the protein and any number of disconnected
  ligands.  Nonpolymer components are detected automatically, extracted, and
  parameterized with SMIRNOFF.  Polymer and solvent/ion components stay with
  the Amber force field.
* ``--protein protein.pdb --ligand ligand1.sdf ...``
  A protein file plus one or more ligand files.  If the protein file happens
  to contain ligands too, those components are extracted automatically as
  well.  SDF/MOL/MOL2 ligands carry explicit bond orders and protonation
  states; PDB ligands use the RCSB Chemical Component Dictionary (CCD).

The output is a topology/positions PDB and an OpenMM System XML that can be
loaded in the CUDA simulation environment.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlretrieve

import gemmi
from openff.toolkit import Molecule
from openff.toolkit.utils.exceptions import UndefinedStereochemistryError
from openmm import Platform, System, Vec3, XmlSerializer, unit
from openmm.app import (
    Element,
    ForceField,
    HBonds,
    Modeller,
    PDBFile,
    PME,
    Topology,
)
from openmmforcefields.generators import SMIRNOFFTemplateGenerator
from pdbfixer import PDBFixer
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Geometry import Point3D

from forcefield_coverage import check_topology_coverage


BOND_TYPE_TO_CHEM = {
    "SING": Chem.BondType.SINGLE,
    "DOUB": Chem.BondType.DOUBLE,
    "TRIP": Chem.BondType.TRIPLE,
    "AROM": Chem.BondType.AROMATIC,
}
CHEM_TO_OMM_BOND = {
    Chem.BondType.SINGLE: "SINGLE",
    Chem.BondType.DOUBLE: "DOUBLE",
    Chem.BondType.TRIPLE: "TRIPLE",
    Chem.BondType.AROMATIC: "AROMATIC",
}
_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base36(value: int, width: int = 2) -> str:
    if value < 0:
        raise ValueError("Value must be non-negative")
    digits = []
    while value:
        value, rem = divmod(value, 36)
        digits.append(_ALPHABET[rem])
    text = "".join(reversed(digits)) or "0"
    return text.rjust(width, "0")


def _ligand_atom_name(ligand_index: int, atom_index: int) -> str:
    """Return a unique PDB-safe atom name (at most four characters)."""
    if not 1 <= ligand_index <= 35:
        raise ValueError(
            "At most 35 ligand molecules are supported by the naming scheme"
        )
    return f"L{_ALPHABET[ligand_index]}{_base36(atom_index, 2)}"


def _ligand_residue_name(ligand_index: int) -> str:
    """Return a three-character residue name for a ligand."""
    if not 1 <= ligand_index <= 1295:
        raise ValueError("Too many ligand molecules for three-character residue names")
    return f"L{_base36(ligand_index, 2)}"


@dataclass(frozen=True)
class CCDResidue:
    atoms: dict[str, tuple[str, int, bool]]
    bonds: list[tuple[str, str, Chem.BondType]]


class CCDResolver:
    """Fetch and cache RCSB Chemical Component Dictionary CIF files."""

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, CCDResidue] = {}

    def get(self, residue_name: str) -> CCDResidue:
        name = residue_name.strip().upper()
        if name in self._cache:
            return self._cache[name]

        path = self.cache_dir / f"{name}.cif"
        if not path.exists():
            url = f"https://files.rcsb.org/ligands/download/{name}.cif"
            try:
                urlretrieve(url, path)
            except (HTTPError, URLError) as exc:
                raise RuntimeError(
                    f"Could not download CCD definition for {name!r} from {url}. "
                    "Use an SDF/MOL2 ligand file for non-RCSB chemistry, or "
                    "pre-populate the CCD cache."
                ) from exc

        block = gemmi.cif.read_file(str(path)).sole_block()
        atoms: dict[str, tuple[str, int, bool]] = {}
        for row in block.find(
            "_chem_comp_atom.",
            ["atom_id", "type_symbol", "charge", "pdbx_aromatic_flag"],
        ):
            charge_text = row[2].strip()
            charge = int(charge_text) if charge_text not in {"", "?", "."} else 0
            atoms[row[0]] = (row[1], charge, row[3] == "Y")

        bonds: list[tuple[str, str, Chem.BondType]] = []
        for row in block.find(
            "_chem_comp_bond.",
            ["atom_id_1", "atom_id_2", "value_order", "pdbx_aromatic_flag"],
        ):
            if row[3] == "Y" or row[2] == "AROM":
                bond_type = Chem.BondType.AROMATIC
            else:
                bond_type = BOND_TYPE_TO_CHEM.get(row[2], Chem.BondType.SINGLE)
            bonds.append((row[0], row[1], bond_type))

        resolved = CCDResidue(atoms=atoms, bonds=bonds)
        self._cache[name] = resolved
        return resolved


@dataclass
class PreparedLigand:
    molecule: Molecule
    rdkit_molecule: Chem.Mol
    source: str
    label: str
    index: int


def _augment_pdb_connectivity(path: Path) -> Path | None:
    """Add inferred peptide/disulfide CONECT records for nonstandard PDBs.

    A standalone ligand PDB often has no LINK/CONECT records.  PDBFixer then
    treats every residue as a free terminal residue and adds extra terminal
    atoms, which breaks peptide ligands and their disulfides.  This helper
    infers adjacent same-chain C-N links and SG-SG disulfides from geometry
    and writes a temporary PDB with the missing CONECT records.

    Returns the temporary path, or None when no missing inter-residue link is
    found or the file is not a PDB.
    """
    if path.suffix.lower() != ".pdb":
        return None

    lines = path.read_text().splitlines()
    atoms: list[dict] = []
    residue_order: dict[tuple[str, str, str], int] = {}
    residue_names: set[str] = set()
    existing_pairs: set[tuple[int, int]] = set()

    for line in lines:
        record = line[:6].strip()
        if record == "CONECT":
            serials = [
                int(line[index : index + 5])
                for index in range(6, len(line), 5)
                if line[index : index + 5].strip().isdigit()
            ]
            for other in serials[1:]:
                existing_pairs.add(tuple(sorted((serials[0], other))))
            continue
        if record not in {"ATOM", "HETATM"}:
            continue
        try:
            serial = int(line[6:11])
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except ValueError:
            continue
        residue_name = line[17:20].strip()
        chain = line[21].strip()
        residue_id = line[22:27].strip()
        key = (chain, residue_id, residue_name)
        if key not in residue_order:
            residue_order[key] = len(residue_order)
        residue_names.add(residue_name)
        atoms.append(
            {
                "serial": serial,
                "name": line[12:16].strip(),
                "residue_key": key,
                "residue_order": residue_order[key],
                "residue_name": residue_name,
                "chain": chain,
                "xyz": Vec3(x / 10.0, y / 10.0, z / 10.0),
            }
        )

    if not atoms:
        return None
    has_nonstandard = any(
        name not in PDBFile._standardResidues for name in residue_names
    )
    sulfur_atoms = [atom for atom in atoms if atom["name"] == "SG"]
    if not has_nonstandard and len(sulfur_atoms) < 2:
        return None

    # LINK/SSBOND records also imply connectivity even when CONECT is absent.
    atom_lookup = {
        (atom["chain"], atom["residue_key"][1], atom["name"]): atom["serial"]
        for atom in atoms
    }
    for line in lines:
        record = line[:6].strip()
        if record == "SSBOND":
            chain_1 = line[15].strip()
            residue_1 = line[17:21].strip() + line[21:22].strip()
            chain_2 = line[29].strip()
            residue_2 = line[31:35].strip() + line[35:36].strip()
            serial_1 = atom_lookup.get((chain_1, residue_1, "SG"))
            serial_2 = atom_lookup.get((chain_2, residue_2, "SG"))
            if serial_1 is not None and serial_2 is not None:
                existing_pairs.add(tuple(sorted((serial_1, serial_2))))
        elif record == "LINK":
            atom_name_1 = line[12:16].strip()
            chain_1 = line[21].strip()
            residue_1 = line[22:26].strip() + line[26:27].strip()
            atom_name_2 = line[42:46].strip()
            chain_2 = line[51].strip()
            residue_2 = line[52:56].strip() + line[56:57].strip()
            serial_1 = atom_lookup.get((chain_1, residue_1, atom_name_1))
            serial_2 = atom_lookup.get((chain_2, residue_2, atom_name_2))
            if serial_1 is not None and serial_2 is not None:
                existing_pairs.add(tuple(sorted((serial_1, serial_2))))

    new_pairs: set[tuple[int, int]] = set()

    def distance_nm(atom_i: dict, atom_j: dict) -> float:
        delta = atom_i["xyz"] - atom_j["xyz"]
        return (delta.x * delta.x + delta.y * delta.y + delta.z * delta.z) ** 0.5

    # Only C-N and SG-SG pairs can be inferred, so avoid an all-atoms O(n^2)
    # scan on large complexes.
    carbon_atoms = [atom for atom in atoms if atom["name"] == "C"]
    nitrogen_atoms = [atom for atom in atoms if atom["name"] == "N"]
    for atom_i in carbon_atoms:
        for atom_j in nitrogen_atoms:
            if atom_i["residue_key"] == atom_j["residue_key"]:
                continue
            both_standard = (
                atom_i["residue_name"] in PDBFile._standardResidues
                and atom_j["residue_name"] in PDBFile._standardResidues
            )
            if both_standard:
                continue
            if atom_i["chain"] != atom_j["chain"]:
                continue
            if abs(atom_i["residue_order"] - atom_j["residue_order"]) != 1:
                continue
            pair = tuple(sorted((atom_i["serial"], atom_j["serial"])))
            if pair in existing_pairs or pair in new_pairs:
                continue
            if distance_nm(atom_i, atom_j) <= 0.17:
                new_pairs.add(pair)

    for i, atom_i in enumerate(sulfur_atoms):
        for atom_j in sulfur_atoms[i + 1 :]:
            pair = tuple(sorted((atom_i["serial"], atom_j["serial"])))
            if pair in existing_pairs or pair in new_pairs:
                continue
            if distance_nm(atom_i, atom_j) <= 0.25:
                new_pairs.add(pair)

    if not new_pairs:
        return None

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".pdb",
        prefix="openmm-ligand-",
        delete=False,
    )
    try:
        body = [
            line
            for line in lines
            if line.strip() not in {"END", "ENDMDL"}
        ]
        handle.write("\n".join(body))
        handle.write("\n")
        for serial_1, serial_2 in sorted(new_pairs):
            handle.write(f"CONECT{serial_1:5d}{serial_2:5d}\n")
            handle.write(f"CONECT{serial_2:5d}{serial_1:5d}\n")
        handle.write("END\n")
        handle.close()
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise
    return Path(handle.name)


def _split_peptide_chains_at_gaps(
    topology: Topology,
    positions: unit.Quantity,
) -> Topology:
    """Split peptide chains where consecutive residues are not bonded.

    PDBFixer calls ``Topology.createStandardBonds()`` after it loads a
    structure.  If missing loops are not rebuilt, residues on either side of an
    unresolved gap become adjacent in the topology and PDBFixer creates a
    peptide bond across the gap.  The resulting bond can be several nanometers
    long and produces enormous forces.  Splitting the chain at each such gap
    before PDBFixer adds terminal atoms makes both sides proper chain termini.
    """
    if topology.getNumAtoms() == 0:
        return topology

    def peptide_like(residue) -> bool:
        names = {atom.name for atom in residue.atoms()}
        return "N" in names and "CA" in names

    def distance(atom_1, atom_2) -> float:
        delta = positions[atom_1.index] - positions[atom_2.index]
        return unit.norm(delta).value_in_unit(unit.nanometer)

    original_ids = {chain.id for chain in topology.chains()}
    alphabet = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    )
    used_ids: set[str] = set()

    def next_chain_id() -> str:
        for candidate in alphabet:
            if candidate not in original_ids and candidate not in used_ids:
                used_ids.add(candidate)
                return candidate
        # More segments than single-character IDs: keep topology functional
        # even if a PDB writer later truncates the ID.
        index = len(used_ids)
        while f"X{index}" in original_ids or f"X{index}" in used_ids:
            index += 1
        generated = f"X{index}"
        used_ids.add(generated)
        return generated

    new_topology = Topology()
    atom_map = {}
    assigned_ids: set[str] = set()
    for chain in topology.chains():
        residues = list(chain.residues())
        segments: list[list] = []
        current: list = []
        for residue in residues:
            split = False
            if current:
                previous = current[-1]
                if peptide_like(previous) and peptide_like(residue):
                    previous_c = next(
                        (atom for atom in previous.atoms() if atom.name == "C"),
                        None,
                    )
                    current_n = next(
                        (atom for atom in residue.atoms() if atom.name == "N"),
                        None,
                    )
                    if previous_c is None or current_n is None:
                        split = True
                    else:
                        split = distance(previous_c, current_n) > 0.20
            if split:
                segments.append(current)
                current = []
            current.append(residue)
        if current:
            segments.append(current)

        for segment_index, segment in enumerate(segments):
            if segment_index == 0 and chain.id not in assigned_ids:
                chain_id = chain.id
            else:
                chain_id = next_chain_id()
            assigned_ids.add(chain_id)
            new_chain = new_topology.addChain(chain_id)
            for residue in segment:
                new_residue = new_topology.addResidue(
                    residue.name,
                    new_chain,
                    residue.id,
                    residue.insertionCode,
                )
                for atom in residue.atoms():
                    atom_map[atom] = new_topology.addAtom(
                        atom.name, atom.element, new_residue
                    )

    for bond in topology.bonds():
        new_topology.addBond(
            atom_map[bond[0]],
            atom_map[bond[1]],
            bond.type,
            bond.order,
        )
    unit_cell = topology.getUnitCellDimensions()
    if unit_cell is not None:
        new_topology.setUnitCellDimensions(unit_cell)
    return new_topology


def _read_pdb_fixer(
    path: Path,
    *,
    ph: float,
    add_missing_residues: bool,
) -> tuple[Topology, unit.Quantity]:
    # A standalone PDB ligand may lack connectivity metadata.  PDBFixer needs
    # the links before it decides which terminal atoms to add.
    augmented_path = _augment_pdb_connectivity(path)
    fixer_path = augmented_path if augmented_path is not None else path
    try:
        # PDBFixer only needs a CPU context for hydrogen placement.  Forcing
        # the CPU platform avoids accidentally selecting a CUDA build in the
        # parameterization environment that may target a different GPU/driver.
        # A single CPU thread also makes PDBFixer's hydrogen minimization
        # bit-for-bit reproducible; the OpenMM CPU platform otherwise rounds
        # reductions differently depending on thread scheduling.
        cpu_platform = Platform.getPlatformByName("CPU")
        if "OPENMM_CPU_THREADS" not in os.environ:
            cpu_platform.setPropertyDefaultValue("Threads", "1")
        fixer = PDBFixer(
            filename=str(fixer_path),
            platform=cpu_platform,
        )
        fixer.findMissingResidues()
        if not add_missing_residues:
            fixer.missingResidues = {}
            fixer.topology = _split_peptide_chains_at_gaps(
                fixer.topology, fixer.positions
            )
        fixer.findMissingAtoms()
        fixer.addMissingAtoms(seed=0)
        # addMissingHydrogens starts each new H at a random position and then
        # minimizes it.  Seed immediately before the call to keep the initial
        # placement repeatable; the subsequent minimizer may still introduce
        # tiny run-to-run coordinate differences.
        random.seed(0)
        fixer.addMissingHydrogens(ph)
        return fixer.topology, fixer.positions
    except Exception as exc:
        raise RuntimeError(
            f"PDBFixer could not prepare {path}: {exc}.  For non-RCSB or "
            "unusual ligand chemistry, provide the ligand separately as an "
            "SDF/MOL2 file with explicit hydrogens, bonds, and charges."
        ) from exc
    finally:
        if augmented_path is not None:
            augmented_path.unlink(missing_ok=True)


def _connected_components(topology: Topology) -> list[list]:
    """Return connected atom groups, each sorted by atom index."""
    atoms = list(topology.atoms())
    adjacency: dict[int, set[int]] = {atom.index: set() for atom in atoms}
    for atom_1, atom_2 in topology.bonds():
        adjacency[atom_1.index].add(atom_2.index)
        adjacency[atom_2.index].add(atom_1.index)

    visited: set[int] = set()
    components: list[list] = []
    for atom in atoms:
        if atom.index in visited:
            continue
        stack = [atom.index]
        visited.add(atom.index)
        component = []
        while stack:
            index = stack.pop()
            component.append(atoms[index])
            for neighbor in adjacency[index]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component, key=lambda item: item.index))
    return components


def _residues_for_atoms(atoms: list) -> list:
    return sorted({atom.residue for atom in atoms}, key=lambda residue: residue.index)


def _component_label(
    component: list,
    *,
    source_name: str,
    component_index: int,
) -> str:
    residues = _residues_for_atoms(component)
    chain_ids = ",".join(sorted({residue.chain.id for residue in residues}))
    residue_text = "-".join(f"{residue.name}{residue.id}" for residue in residues)
    if len(residue_text) > 90:
        residue_text = residue_text[:87] + "..."
    return (
        f"{source_name} component {component_index} "
        f"(chain {chain_ids}: {residue_text})"
    )


def _is_standard_residue(forcefield: ForceField, residue) -> bool:
    return (
        residue.name in forcefield._templates
        or residue.name in PDBFile._standardResidues
    )


def _classify_components(
    topology: Topology,
    components: list[list],
    forcefield: ForceField,
    *,
    max_ligand_residues: int,
) -> tuple[list[list], list[list]]:
    """Split components into standard polymer/solvent and ligand groups.

    A component is a ligand if any residue in it has no template in the
    protein/water force field.  This intentionally treats a short D-peptide or
    a residue with a covalent modification as one ligand molecule.  Large
    mixed components are rejected because merging a whole protein chain into a
    single SMIRNOFF residue is not a sensible interpretation.
    """
    polymer_components: list[list] = []
    ligand_components: list[list] = []
    for component in components:
        residues = _residues_for_atoms(component)
        nonstandard = [
            residue
            for residue in residues
            if not _is_standard_residue(forcefield, residue)
        ]
        if not nonstandard:
            polymer_components.append(component)
            continue
        if max_ligand_residues > 0 and len(residues) > max_ligand_residues:
            names = ", ".join(sorted({residue.name for residue in nonstandard}))
            raise RuntimeError(
                f"A connected component with {len(residues)} residues contains "
                f"nonstandard residue type(s) {names}.  It is too large to treat "
                "as one SMIRNOFF ligand.  Provide the ligand separately (SDF/MOL2) "
                "or increase --max-ligand-residues deliberately."
            )
        ligand_components.append(component)
    return polymer_components, ligand_components


def _copy_components(
    topology: Topology,
    positions_nm: list[Vec3],
    components: list[list],
) -> tuple[Topology, list[Vec3]]:
    """Copy selected connected components into a fresh topology."""
    new_topology = Topology()
    old_to_new: dict = {}
    chain_map: dict[tuple[int, str], Topology.Chain] = {}
    new_positions: list[Vec3] = []

    for component in components:
        component_atoms = set(component)
        for residue in _residues_for_atoms(component):
            old_chain = residue.chain
            chain_key = (old_chain.index, old_chain.id)
            if chain_key not in chain_map:
                chain_map[chain_key] = new_topology.addChain(old_chain.id)
            new_residue = new_topology.addResidue(
                residue.name,
                chain_map[chain_key],
                residue.id,
            )
            for atom in sorted(residue.atoms(), key=lambda item: item.index):
                formal_charge = getattr(atom, "formalCharge", 0) or 0
                new_atom = new_topology.addAtom(
                    atom.name,
                    atom.element,
                    new_residue,
                    formalCharge=formal_charge,
                )
                old_to_new[atom] = new_atom
                new_positions.append(positions_nm[atom.index])

        for bond in topology.bonds():
            atom_1, atom_2 = bond
            if (
                atom_1 in old_to_new
                and atom_2 in old_to_new
                and atom_1 in component_atoms
                and atom_2 in component_atoms
            ):
                order = getattr(bond, "order", None)
                new_topology.addBond(
                    old_to_new[atom_1],
                    old_to_new[atom_2],
                    order=order,
                )

    return new_topology, new_positions


def _fix_rdkit_charges(molecule: Chem.Mol) -> None:
    """Correct the most common formal-charge issues in CCD-derived graphs.

    PDBFixer and the CCD describe an isolated residue.  In a peptide, amide
    nitrogen atoms are three-coordinate, but protonated Lys/Arg nitrogen atoms
    are four-coordinate.  A terminal carboxylate oxygen without an attached
    hydrogen is assigned a -1 charge.  Esters and other C-O-C groups are left
    unchanged.  Custom protonation states should be supplied as SDF/MOL2.
    """
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() == 7 and atom.GetDegree() == 4:
            atom.SetFormalCharge(1)

    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        oxygens = [n for n in atom.GetNeighbors() if n.GetAtomicNum() == 8]
        if len(oxygens) != 2:
            continue
        single_oxygens = [
            oxygen
            for oxygen in oxygens
            if (
                molecule.GetBondBetweenAtoms(
                    atom.GetIdx(), oxygen.GetIdx()
                ).GetBondType()
                == Chem.BondType.SINGLE
            )
        ]
        if len(single_oxygens) != 1:
            continue
        oxygen = single_oxygens[0]
        has_hydrogen = any(n.GetAtomicNum() == 1 for n in oxygen.GetNeighbors())
        has_other_carbon = any(
            n.GetAtomicNum() == 6 and n.GetIdx() != atom.GetIdx()
            for n in oxygen.GetNeighbors()
        )
        if not has_hydrogen and not has_other_carbon and oxygen.GetFormalCharge() == 0:
            oxygen.SetFormalCharge(-1)


def _protonate_n_termini(
    rw_molecule: Chem.RWMol,
    rd_to_openmm: dict[int, object],
    rd_positions: dict[int, Vec3],
) -> None:
    """Protonate free N-terminal amines in nonstandard peptide residues.

    PDBFixer knows how to build standard N-terminal residues, but it treats a
    nonstandard D-amino acid as an isolated residue and may leave its backbone
    amine neutral (for example DPN in the 7YAE D-peptide).  At pH 7.4 that
    amine should be an ammonium.  Add the missing hydrogen(s) and let
    ``_fix_rdkit_charges`` assign the +1 formal charge.

    Only backbone atoms named ``N`` in residues containing ``CA`` are
    considered, and amide nitrogens (directly bonded to a carbonyl carbon) are
    excluded.  Ligands without amino-acid-like backbones are left untouched.
    """
    for rd_index in list(rd_to_openmm):
        atom = rw_molecule.GetAtomWithIdx(rd_index)
        if atom.GetAtomicNum() != 7 or atom.GetFormalCharge() != 0:
            continue
        if atom.GetIsAromatic() or atom.GetDegree() >= 4:
            continue
        openmm_atom = rd_to_openmm[rd_index]
        if openmm_atom.name != "N":
            continue
        residue = openmm_atom.residue
        if "CA" not in {backbone_atom.name for backbone_atom in residue.atoms()}:
            continue
        if not any(
            neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors()
        ):
            continue

        # An amide N is directly bonded to a carbonyl carbon.  The N-terminus
        # is not, even though its CA is bonded to the residue carbonyl.
        is_amide = False
        for neighbor in atom.GetNeighbors():
            if neighbor.GetAtomicNum() != 6:
                continue
            if any(
                bond.GetOtherAtom(neighbor).GetAtomicNum() == 8
                and bond.GetBondType() == Chem.BondType.DOUBLE
                for bond in neighbor.GetBonds()
            ):
                is_amide = True
                break
        if is_amide:
            continue

        while atom.GetDegree() < 4:
            nitrogen_position = rd_positions[rd_index]
            vectors = []
            for neighbor in atom.GetNeighbors():
                neighbor_position = rd_positions[neighbor.GetIdx()]
                vectors.append(
                    (
                        neighbor_position.x - nitrogen_position.x,
                        neighbor_position.y - nitrogen_position.y,
                        neighbor_position.z - nitrogen_position.z,
                    )
                )
            sx = sum(vector[0] for vector in vectors)
            sy = sum(vector[1] for vector in vectors)
            sz = sum(vector[2] for vector in vectors)
            norm = (sx * sx + sy * sy + sz * sz) ** 0.5
            if norm > 1e-8:
                direction = (-sx / norm, -sy / norm, -sz / norm)
            else:
                # Degenerate geometry: choose any direction perpendicular to
                # the first existing bond.
                vx, vy, vz = vectors[0]
                if abs(vx) <= abs(vy) and abs(vx) <= abs(vz):
                    direction = (0.0, -vz, vy)
                elif abs(vy) <= abs(vz):
                    direction = (-vz, 0.0, vx)
                else:
                    direction = (-vy, vx, 0.0)
                length = (
                    direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2
                ) ** 0.5
                direction = (
                    direction[0] / length,
                    direction[1] / length,
                    direction[2] / length,
                )

            hydrogen = Chem.Atom(1)
            hydrogen.SetNoImplicit(True)
            hydrogen_index = rw_molecule.AddAtom(hydrogen)
            rw_molecule.AddBond(rd_index, hydrogen_index, Chem.BondType.SINGLE)
            rd_positions[hydrogen_index] = Vec3(
                nitrogen_position.x + direction[0] * 0.101,
                nitrogen_position.y + direction[1] * 0.101,
                nitrogen_position.z + direction[2] * 0.101,
            )
            atom = rw_molecule.GetAtomWithIdx(rd_index)


def _infer_inter_residue_bonds(
    rw_molecule: Chem.RWMol,
    atoms: list,
    positions_nm: list[Vec3],
    index_of,
    existing: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Infer peptide and disulfide bonds when a PDB lacks LINK/CONECT data."""
    added = set(existing)
    for i, atom_i in enumerate(atoms):
        for j in range(i + 1, len(atoms)):
            atom_j = atoms[j]
            if atom_i.residue is atom_j.residue:
                continue
            pair = tuple(sorted((index_of[atom_i], index_of[atom_j])))
            if pair in added:
                continue

            delta = positions_nm[atom_i.index] - positions_nm[atom_j.index]
            distance_nm = (
                delta.x * delta.x + delta.y * delta.y + delta.z * delta.z
            ) ** 0.5

            is_peptide = (
                {atom_i.name, atom_j.name} == {"C", "N"}
                and distance_nm <= 0.17
            )
            is_disulfide = (
                atom_i.name == "SG"
                and atom_j.name == "SG"
                and distance_nm <= 0.25
            )
            if is_peptide or is_disulfide:
                rw_molecule.AddBond(*pair, Chem.BondType.SINGLE)
                added.add(pair)
    return added


def _rdkit_from_pdb_ligand(
    topology: Topology,
    positions_nm: list[Vec3],
    ccd: CCDResolver,
    *,
    atom_indices: set[int] | None = None,
) -> Chem.Mol:
    """Build an RDKit molecule for one connected PDB ligand component.

    Intra-residue bond orders and formal charges come from the CCD.  Inter-
    residue bonds come from the PDB topology, or are inferred from peptide and
    disulfide geometry when the PDB has no LINK/CONECT records.
    """
    if atom_indices is None:
        all_atoms = list(topology.atoms())
    else:
        all_atoms = [
            atom for atom in topology.atoms() if atom.index in atom_indices
        ]
    if not all_atoms:
        raise RuntimeError("Cannot build a ligand molecule from an empty component")

    residues = {atom.residue for atom in all_atoms}
    ccd_data = {residue.name: ccd.get(residue.name) for residue in residues}

    index_of = {atom: i for i, atom in enumerate(all_atoms)}
    selected = set(all_atoms)

    rw_molecule = Chem.RWMol()
    for atom in all_atoms:
        try:
            symbol, charge, aromatic = ccd_data[atom.residue.name].atoms[atom.name]
        except KeyError as exc:
            raise RuntimeError(
                f"Atom {atom.name!r} in residue {atom.residue.name!r} is not in "
                "the CCD definition.  Use an SDF/MOL2 ligand file with explicit "
                "atom names and bonds for this ligand."
            ) from exc
        rd_atom = Chem.Atom(symbol)
        rd_atom.SetFormalCharge(charge)
        rd_atom.SetNoImplicit(True)
        rd_atom.SetIsAromatic(aromatic)
        rd_atom.SetProp("_Name", atom.name)
        rw_molecule.AddAtom(rd_atom)

    added: set[tuple[int, int]] = set()
    for residue in residues:
        local = {atom.name: atom for atom in residue.atoms() if atom in selected}
        for name_1, name_2, bond_type in ccd_data[residue.name].bonds:
            if name_1 in local and name_2 in local:
                pair = tuple(
                    sorted((index_of[local[name_1]], index_of[local[name_2]]))
                )
                rw_molecule.AddBond(*pair, bond_type)
                added.add(pair)

    for bond in topology.bonds():
        atom_1, atom_2 = bond
        if atom_1 not in selected or atom_2 not in selected:
            continue
        pair = tuple(sorted((index_of[atom_1], index_of[atom_2])))
        if pair not in added:
            rw_molecule.AddBond(*pair, Chem.BondType.SINGLE)
            added.add(pair)

    added = _infer_inter_residue_bonds(
        rw_molecule, all_atoms, positions_nm, index_of, added
    )

    rd_to_openmm = {index_of[atom]: atom for atom in all_atoms}
    rd_positions = {
        index_of[atom]: positions_nm[atom.index] for atom in all_atoms
    }
    _protonate_n_termini(rw_molecule, rd_to_openmm, rd_positions)

    molecule = rw_molecule.GetMol()
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for atom_index, position in rd_positions.items():
        conformer.SetAtomPosition(
            atom_index,
            Point3D(position.x * 10, position.y * 10, position.z * 10),
        )
    molecule.AddConformer(conformer)

    _fix_rdkit_charges(molecule)
    Chem.SanitizeMol(molecule)
    Chem.AssignStereochemistryFrom3D(molecule, replaceExistingTags=True)
    return molecule


def _load_rdkit_records(path: Path) -> list[Chem.Mol]:
    suffix = path.suffix.lower()
    if suffix in {".sdf", ".sd"}:
        supplier = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=True)
        molecules = [mol for mol in supplier if mol is not None]
        if not molecules:
            raise RuntimeError(f"No readable molecules found in {path}")
        return molecules
    if suffix == ".mol":
        molecule = Chem.MolFromMolFile(str(path), removeHs=False, sanitize=True)
        if molecule is None:
            raise RuntimeError(f"Could not read MOL file {path}")
        return [molecule]
    if suffix == ".mol2":
        molecule = Chem.MolFromMol2File(str(path), removeHs=False, sanitize=True)
        if molecule is None:
            raise RuntimeError(f"Could not read MOL2 file {path}")
        return [molecule]
    raise RuntimeError(
        f"Unsupported ligand file format {path.suffix!r} for {path}. "
        "Supported formats are SDF, MOL, MOL2, and PDB."
    )


def _prepare_rdkit_molecule(molecule: Chem.Mol, *, label: str) -> Chem.Mol:
    has_3d = (
        molecule.GetNumConformers() > 0
        and molecule.GetConformer().Is3D()
    )
    molecule = Chem.AddHs(molecule, addCoords=has_3d)
    if molecule.GetNumConformers() == 0 or not molecule.GetConformer().Is3D():
        if AllChem.EmbedMolecule(molecule, randomSeed=0xF00D) != 0:
            raise RuntimeError(
                f"Could not generate 3D coordinates for ligand {label!r}. "
                "Provide a 3D SDF/MOL2 file."
            )
        AllChem.MMFFOptimizeMolecule(molecule)
    Chem.AssignStereochemistry(molecule, cleanIt=True, force=True)
    return molecule


def _make_openff_molecule(
    rdkit_molecule: Chem.Mol,
    *,
    ligand_index: int,
    label: str,
    allow_undefined_stereo: bool,
) -> Molecule:
    for atom_index, atom in enumerate(rdkit_molecule.GetAtoms()):
        atom.SetProp("_Name", _ligand_atom_name(ligand_index, atom_index))

    try:
        return Molecule.from_rdkit(
            rdkit_molecule,
            allow_undefined_stereo=allow_undefined_stereo,
            hydrogens_are_explicit=True,
        )
    except UndefinedStereochemistryError as exc:
        raise RuntimeError(
            f"Ligand {label!r} has undefined stereochemistry.  Supply a fully "
            "specified 3D SDF/MOL2 file, or rerun with --allow-undefined-stereo."
        ) from exc


def _add_ligand_to_topology(
    topology: Topology,
    positions_nm: list[Vec3],
    ligand: PreparedLigand,
    *,
    chain: Topology.Chain,
) -> None:
    residue = topology.addResidue(
        _ligand_residue_name(ligand.index), chain, str(ligand.index)
    )
    rdkit_molecule = ligand.rdkit_molecule
    conformer = rdkit_molecule.GetConformer()
    rd_to_openmm = {}

    for atom_index, atom in enumerate(rdkit_molecule.GetAtoms()):
        name = atom.GetProp("_Name")
        new_atom = topology.addAtom(
            name,
            Element.getByAtomicNumber(atom.GetAtomicNum()),
            residue,
            formalCharge=int(atom.GetFormalCharge()),
        )
        rd_to_openmm[atom_index] = new_atom
        point = conformer.GetAtomPosition(atom_index)
        positions_nm.append(Vec3(point.x / 10.0, point.y / 10.0, point.z / 10.0))

    for bond in rdkit_molecule.GetBonds():
        topology.addBond(
            rd_to_openmm[bond.GetBeginAtomIdx()],
            rd_to_openmm[bond.GetEndAtomIdx()],
            order=CHEM_TO_OMM_BOND[bond.GetBondType()],
        )


def _unused_chain_id(topology: Topology, preferred: str = "L") -> str:
    used = {chain.id for chain in topology.chains()}
    if preferred not in used:
        return preferred
    for character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
        if character not in used:
            return character
    return preferred


def _prepare_ligand(
    rdkit_molecule: Chem.Mol,
    *,
    path: Path,
    label: str,
    ligand_index: int,
    allow_undefined_stereo: bool,
) -> PreparedLigand:
    """Create the OpenFF molecule and bookkeeping for one ligand record."""
    openff_molecule = _make_openff_molecule(
        rdkit_molecule,
        ligand_index=ligand_index,
        label=label,
        allow_undefined_stereo=allow_undefined_stereo,
    )
    return PreparedLigand(
        molecule=openff_molecule,
        rdkit_molecule=rdkit_molecule,
        source=str(path),
        label=label,
        index=ligand_index,
    )


def _load_ligands(
    paths: list[Path],
    *,
    ph: float,
    add_missing_residues: bool,
    ccd: CCDResolver,
    allow_undefined_stereo: bool,
    start_index: int = 1,
) -> list[PreparedLigand]:
    ligands: list[PreparedLigand] = []
    ligand_index = start_index - 1
    for path in paths:
        suffix = path.suffix.lower()
        if suffix in {".sdf", ".sd", ".mol", ".mol2"}:
            records = _load_rdkit_records(path)
            for record_index, record in enumerate(records, 1):
                ligand_index += 1
                label = (
                    f"{path.name}:{record_index}"
                    if suffix in {".sdf", ".sd"} and len(records) > 1
                    else path.name
                )
                rdkit_molecule = _prepare_rdkit_molecule(record, label=label)
                ligands.append(
                    _prepare_ligand(
                        rdkit_molecule,
                        path=path,
                        label=label,
                        ligand_index=ligand_index,
                        allow_undefined_stereo=allow_undefined_stereo,
                    )
                )
        elif suffix in {".pdb", ".cif", ".mmcif"}:
            # A ligand PDB/mmCIF file is one ligand molecule.  Do not split it
            # by topology connectivity: small/PDB ligand files often have no
            # CONECT records, and splitting would turn each atom into a fake
            # "ligand".  PDBFixer + CCD provide the intra-residue bonds, and
            # peptide/disulfide links are inferred from geometry.
            topology, positions = _read_pdb_fixer(
                path, ph=ph, add_missing_residues=add_missing_residues
            )
            positions_nm = [
                positions[i].value_in_unit(unit.nanometer)
                for i in range(len(positions))
            ]
            ligand_index += 1
            rdkit_molecule = _rdkit_from_pdb_ligand(
                topology,
                positions_nm,
                ccd,
            )
            ligands.append(
                _prepare_ligand(
                    rdkit_molecule,
                    path=path,
                    label=path.name,
                    ligand_index=ligand_index,
                    allow_undefined_stereo=allow_undefined_stereo,
                )
            )
        else:
            raise RuntimeError(f"Unsupported ligand file format: {path}")
    return ligands


def _write_report(
    path: Path,
    *,
    source_path: Path,
    source_mode: str,
    ligands: list[PreparedLigand],
    ligand_components: list[list],
    component_labels: list[str],
    protein_coverage: str,
    system: System,
    topology: Topology,
    ligand_forcefield: str,
) -> None:
    lines = [
        "System preparation report",
        "========================",
        f"Input: {source_path}",
        f"Input mode: {source_mode}",
        "Protein force field: Amber",
        f"Ligand force field: {ligand_forcefield}",
        f"Ligand components detected in the input structure: {len(ligand_components)}",
    ]
    for label in component_labels:
        lines.append(f"  - {label}")
    lines.append(f"Ligand molecules parameterized: {len(ligands)}")
    for ligand in ligands:
        lines.append(
            f"  {ligand.index}. {ligand.label}: {ligand.molecule.n_atoms} atoms, "
            f"charge {ligand.molecule.total_charge}, source {ligand.source}"
        )
    lines.extend(
        [
            "",
            "Protein coverage",
            "----------------",
            protein_coverage,
            "",
            "Prepared system",
            "---------------",
            f"Atoms in topology: {topology.getNumAtoms()}",
            f"Particles in system: {system.getNumParticles()}",
            f"Forces: {system.getNumForces()}",
        ]
    )
    box = topology.getPeriodicBoxVectors()
    if box is not None:
        box_nm = [vector.value_in_unit(unit.nanometer) for vector in box]
        lines.append(
            "Periodic box (nm): "
            + ", ".join(f"({v.x:.3f}, {v.y:.3f}, {v.z:.3f})" for v in box_nm)
        )
    path.write_text("\n".join(lines) + "\n")


def prepare_system(
    *,
    protein_path: Path | None,
    complex_path: Path | None,
    ligand_paths: list[Path],
    output_dir: Path,
    forcefields: list[str],
    ligand_forcefield: str,
    ph: float,
    padding_nm: float,
    ionic_strength_molar: float,
    ccd_cache: Path,
    add_missing_residues: bool,
    allow_undefined_stereo: bool,
    max_ligand_residues: int,
) -> tuple[Path, Path, Path]:
    if (protein_path is None) == (complex_path is None):
        raise ValueError("Supply exactly one of protein_path or complex_path")
    if complex_path is not None and ligand_paths:
        raise ValueError(
            "--complex already contains the ligands; do not also pass --ligand"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    ccd = CCDResolver(ccd_cache)
    source_path = complex_path if complex_path is not None else protein_path
    assert source_path is not None
    source_mode = (
        "single complex file; disconnected ligands auto-detected"
        if complex_path is not None
        else "protein file plus separate ligand files; embedded ligands auto-detected"
    )

    source_topology, source_positions = _read_pdb_fixer(
        source_path, ph=ph, add_missing_residues=add_missing_residues
    )
    source_positions_nm = [
        source_positions[i].value_in_unit(unit.nanometer)
        for i in range(len(source_positions))
    ]

    forcefield = ForceField(*forcefields)
    components = _connected_components(source_topology)
    protein_components, ligand_components = _classify_components(
        source_topology,
        components,
        forcefield,
        max_ligand_residues=max_ligand_residues,
    )
    if not protein_components:
        raise RuntimeError(
            "No standard protein/solvent component was found in the input.  "
            "The input appears to contain only ligands."
        )

    component_labels = [
        _component_label(
            component,
            source_name=source_path.name,
            component_index=index,
        )
        for index, component in enumerate(ligand_components, 1)
    ]
    if ligand_components:
        print("Detected ligand components needing SMIRNOFF:")
        for label in component_labels:
            print(f"  - {label}", flush=True)

    topology, positions_nm = _copy_components(
        source_topology,
        source_positions_nm,
        protein_components,
    )

    coverage = check_topology_coverage(
        topology,
        forcefield,
        path=source_path,
        forcefield_files=forcefields,
    )
    coverage_text = coverage.format(max_details=20)
    print("Protein force-field coverage check")
    print(coverage_text, flush=True)
    if not coverage.fully_covered:
        raise RuntimeError(
            "The input contains polymer/solvent residues that the Amber force "
            "field cannot parameterize.  See the coverage report above."
        )

    ligands = _load_ligands(
        ligand_paths,
        ph=ph,
        add_missing_residues=add_missing_residues,
        ccd=ccd,
        allow_undefined_stereo=allow_undefined_stereo,
        start_index=1,
    )

    for component_index, component in enumerate(ligand_components, 1):
        ligand_index = len(ligands) + 1
        label = component_labels[component_index - 1]
        rdkit_molecule = _rdkit_from_pdb_ligand(
            source_topology,
            source_positions_nm,
            ccd,
            atom_indices={atom.index for atom in component},
        )
        openff_molecule = _make_openff_molecule(
            rdkit_molecule,
            ligand_index=ligand_index,
            label=label,
            allow_undefined_stereo=allow_undefined_stereo,
        )
        ligands.append(
            PreparedLigand(
                molecule=openff_molecule,
                rdkit_molecule=rdkit_molecule,
                source=str(source_path),
                label=label,
                index=ligand_index,
            )
        )

    if ligands:
        ligand_chain = topology.addChain(_unused_chain_id(topology))
        for ligand in ligands:
            _add_ligand_to_topology(
                topology,
                positions_nm,
                ligand,
                chain=ligand_chain,
            )
            print(
                f"Added ligand {ligand.index}: {ligand.label} "
                f"({ligand.molecule.n_atoms} atoms, "
                f"charge {ligand.molecule.total_charge})",
                flush=True,
            )
    else:
        print("No ligand components found; building a protein-only system.", flush=True)

    modeller = Modeller(topology, unit.Quantity(positions_nm, unit.nanometer))
    if ligands:
        generator = SMIRNOFFTemplateGenerator(
            molecules=[ligand.molecule for ligand in ligands],
            forcefield=ligand_forcefield,
        )
        forcefield.registerTemplateGenerator(generator.generator)
        print(
            f"Registered SMIRNOFFTemplateGenerator for {len(ligands)} ligand(s)",
            flush=True,
        )

    modeller.addSolvent(
        forcefield,
        padding=padding_nm,
        ionicStrength=ionic_strength_molar * unit.molar,
    )
    system = forcefield.createSystem(
        modeller.topology,
        nonbondedMethod=PME,
        nonbondedCutoff=1 * unit.nanometer,
        constraints=HBonds,
    )

    prepared_pdb = output_dir / "prepared.pdb"
    system_xml = output_dir / "system.xml"
    report_path = output_dir / "parameterization.txt"
    with prepared_pdb.open("w") as handle:
        PDBFile.writeFile(
            modeller.topology,
            modeller.positions,
            file=handle,
            keepIds=True,
        )
    system_xml.write_text(XmlSerializer.serialize(system))
    _write_report(
        report_path,
        source_path=source_path,
        source_mode=source_mode,
        ligands=ligands,
        ligand_components=ligand_components,
        component_labels=component_labels,
        protein_coverage=coverage_text,
        system=system,
        topology=modeller.topology,
        ligand_forcefield=ligand_forcefield,
    )
    print(f"Wrote {prepared_pdb}")
    print(f"Wrote {system_xml}")
    print(f"Wrote {report_path}")
    return prepared_pdb, system_xml, report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an OpenMM System for a protein with ligands using Amber "
            "for polymers and SMIRNOFF for disconnected ligand components."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--complex",
        type=Path,
        help="Single PDB/mmCIF containing protein and/or ligands.",
    )
    source_group.add_argument(
        "--protein",
        type=Path,
        help="Protein PDB/mmCIF file; use with --ligand for separate ligand files.",
    )
    parser.add_argument(
        "--ligand",
        type=Path,
        action="append",
        default=[],
        help="Ligand file (SDF, MOL, MOL2, PDB, or mmCIF). Repeat for each ligand.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--forcefield",
        action="append",
        dest="forcefields",
        default=None,
        help="Protein/water force-field XML. Repeat as needed.",
    )
    parser.add_argument(
        "--ligand-forcefield",
        default="openff-2.3.0",
        help="SMIRNOFF force field name or OFFXML file (default: openff-2.3.0)",
    )
    parser.add_argument("--ph", type=float, default=7.4)
    parser.add_argument("--padding-nm", type=float, default=1.0)
    parser.add_argument("--ionic-strength-molar", type=float, default=0.15)
    parser.add_argument(
        "--ccd-cache",
        type=Path,
        default=Path.home() / ".cache" / "openmm-parameterizer" / "ccd",
    )
    parser.add_argument(
        "--add-missing-residues",
        action="store_true",
        help="Let PDBFixer rebuild missing protein loops (default: do not build).",
    )
    parser.add_argument(
        "--allow-undefined-stereo",
        action="store_true",
        help="Allow ligands with undefined stereochemistry.",
    )
    parser.add_argument(
        "--max-ligand-residues",
        type=int,
        default=50,
        help=(
            "Maximum residue count for a connected nonstandard component that "
            "is treated as a single ligand (default: 50; 0 disables the limit)."
        ),
    )
    args = parser.parse_args(argv)

    # PDBFixer places new hydrogens at random positions and then minimizes
    # them; Modeller.addSolvent also uses random water/ion placement.  Seed the
    # standard library RNG to remove the avoidable random variation.
    random.seed(0)

    if args.complex is not None and args.ligand:
        parser.error("--complex cannot be combined with --ligand")

    forcefields = args.forcefields or [
        "amber14/protein.ff14SB.xml",
        "amber14/tip3p.xml",
    ]

    try:
        prepare_system(
            protein_path=args.protein,
            complex_path=args.complex,
            ligand_paths=args.ligand,
            output_dir=args.output_dir,
            forcefields=forcefields,
            ligand_forcefield=args.ligand_forcefield,
            ph=args.ph,
            padding_nm=args.padding_nm,
            ionic_strength_molar=args.ionic_strength_molar,
            ccd_cache=args.ccd_cache,
            add_missing_residues=args.add_missing_residues,
            allow_undefined_stereo=args.allow_undefined_stereo,
            max_ligand_residues=args.max_ligand_residues,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
