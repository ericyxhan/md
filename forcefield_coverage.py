#!/usr/bin/env python3
"""Check whether an OpenMM ForceField can parameterize every residue in a structure.

Usage:
    python forcefield_coverage.py STRUCTURE.pdb amber19-all.xml amber19/tip3pfb.xml
    python forcefield_coverage.py STRUCTURE.cif amber19-all.xml amber19/tip3pfb.xml

Exit codes:
    0  every residue matches as-is
    1  every residue type is supported, but preprocessing is needed
       (hydrogens, missing atoms, or terminal groups)
    2  one or more residue types have no matching force-field template
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from openmm.app import ForceField, PDBFile, PDBxFile

try:
    from openmm.app.forcefield import _findMatchErrors
except ImportError:  # pragma: no cover - only relevant for older OpenMM versions
    _findMatchErrors = None


_STANDARD_RESIDUES = set(getattr(PDBFile, "_standardResidues", ()))
_MISSING_H_RE = re.compile(r"missing \d+ H atoms")
_MATCHES_RE = re.compile(r"(?:matches|similar to) ([A-Za-z0-9+\-]+)")


@dataclass(frozen=True)
class ResidueIssue:
    """A residue that OpenMM could not match to a force-field template."""

    index: int
    chain: str
    residue_id: str
    name: str
    category: str
    detail: str
    closest_template: str | None = None

    def __str__(self) -> str:
        location = f"{self.name} {self.residue_id} (chain {self.chain})"
        closest = f"; closest template: {self.closest_template}" if self.closest_template else ""
        return f"{location}: {self.category}{closest}\n    {self.detail}"


@dataclass
class CoverageReport:
    """Result of checking a structure against a ForceField."""

    path: Path
    forcefield_files: tuple[str, ...]
    total_residues: int
    issues: list[ResidueIssue] = field(default_factory=list)
    hydrogens_added: bool | None = None
    hydrogenation_error: str | None = None

    @property
    def fully_covered(self) -> bool:
        """True if every residue matches a template without preprocessing."""
        return not self.issues

    @property
    def nonstandard_issues(self) -> list[ResidueIssue]:
        return [issue for issue in self.issues if issue.category == "nonstandard_residue"]

    @property
    def covered_after_preprocessing(self) -> bool:
        """True if the force field knows every residue type.

        Remaining issues may still require adding hydrogens, missing heavy
        atoms, or terminal groups before ``createSystem`` will succeed.
        """
        return not self.nonstandard_issues

    def format(self, max_details: int = 25) -> str:
        lines = [
            f"Structure: {self.path}",
            f"Force field: {', '.join(self.forcefield_files)}",
            f"Residues: {self.total_residues}",
            f"Fully covered as-is: {'yes' if self.fully_covered else 'no'}",
            f"Covered after preprocessing: {'yes' if self.covered_after_preprocessing else 'no'}",
        ]

        if self.hydrogens_added is not None:
            lines.append(f"addHydrogens succeeded: {'yes' if self.hydrogens_added else 'no'}")
            if self.hydrogenation_error:
                lines.append(f"  {self.hydrogenation_error.splitlines()[0]}")

        if self.issues:
            counts = Counter(issue.category for issue in self.issues)
            lines.extend(["", "Issues by category:"])
            for category, count in counts.most_common():
                lines.append(f"  {category}: {count}")

            if self.nonstandard_issues:
                by_name: dict[str, list[ResidueIssue]] = defaultdict(list)
                for issue in self.nonstandard_issues:
                    by_name[issue.name].append(issue)
                lines.extend(["", "Unparameterized residue types:"])
                for name in sorted(by_name):
                    items = by_name[name]
                    closest = items[0].closest_template or "none"
                    locations = ", ".join(f"{i.chain}:{i.residue_id}" for i in items)
                    lines.append(
                        f"  {name} ({len(items)}): closest template {closest}; at {locations}"
                    )

            lines.extend(["", "Details:"])
            for issue in self.issues[:max_details]:
                lines.append(f"  {issue}")
            hidden = len(self.issues) - max_details
            if hidden > 0:
                lines.append(f"  ... and {hidden} more")

        return "\n".join(lines)


def _load_structure(path: Path):
    """Load a PDB or mmCIF file."""
    if path.suffix.lower() in {".cif", ".mmcif"}:
        return PDBxFile(str(path))
    return PDBFile(str(path))


def _closest_template(detail: str) -> str | None:
    match = _MATCHES_RE.search(detail)
    return match.group(1) if match else None


def _make_issue(forcefield: ForceField, residue) -> ResidueIssue:
    detail = _findMatchErrors(forcefield, residue) if _findMatchErrors else "No template found."

    # A residue name is "standard" if the force field has a template with that
    # name, or if it is one of the standard PDB residue names (e.g. HIS, which
    # addHydrogens resolves to HID/HIE/HIP).
    standard = residue.name in forcefield._templates or residue.name in _STANDARD_RESIDUES

    if not standard:
        category = "nonstandard_residue"
    elif _MISSING_H_RE.search(detail):
        category = "missing_hydrogens"
    elif "externally bonded atoms" in detail or "terminal capping" in detail:
        category = "connectivity"
    else:
        category = "needs_preprocessing"

    return ResidueIssue(
        index=residue.index,
        chain=residue.chain.id,
        residue_id=str(residue.id),
        name=residue.name,
        category=category,
        detail=detail,
        closest_template=_closest_template(detail),
    )


def check_topology_coverage(
    topology,
    forcefield: ForceField,
    *,
    path: str | Path = "<topology>",
    forcefield_files: Sequence[str] = (),
) -> CoverageReport:
    """Check an already-loaded topology against an already-loaded ForceField.

    This avoids re-reading the structure and lets callers run exactly the same
    check that ``check_forcefield_coverage`` performs before ``createSystem``.
    """
    unmatched = forcefield.getUnmatchedResidues(topology)
    return CoverageReport(
        path=Path(path),
        forcefield_files=tuple(forcefield_files),
        total_residues=topology.getNumResidues(),
        issues=[_make_issue(forcefield, residue) for residue in unmatched],
    )


def check_forcefield_coverage(
    pdb_path: str | Path,
    forcefield_files: Sequence[str],
    *,
    try_hydrogens: bool = False,
) -> CoverageReport:
    """Determine whether a ForceField can cover all residues in a structure.

    Parameters
    ----------
    pdb_path:
        Path to a ``.pdb``, ``.cif``, or ``.mmcif`` file.
    forcefield_files:
        XML files passed to :class:`openmm.app.ForceField`, for example
        ``["amber19-all.xml", "amber19/tip3pfb.xml"]``.
    try_hydrogens:
        If True and some residues do not match, try ``Modeller.addHydrogens``
        on an in-memory copy and re-check the result.  This catches missing
        terminal atoms/connectivity problems too.

    Returns
    -------
    CoverageReport
    """
    path = Path(pdb_path)
    if isinstance(forcefield_files, str):
        forcefield_files = [forcefield_files]
    structure = _load_structure(path)
    forcefield = ForceField(*forcefield_files)

    report = check_topology_coverage(
        structure.topology,
        forcefield,
        path=path,
        forcefield_files=forcefield_files,
    )

    if try_hydrogens and report.issues:
        from openmm.app import Modeller

        modeller = Modeller(structure.topology, structure.positions)
        try:
            modeller.addHydrogens(forcefield)
            report.hydrogens_added = True
            remaining = forcefield.getUnmatchedResidues(modeller.topology)
            report.issues = [_make_issue(forcefield, residue) for residue in remaining]
        except Exception as exc:  # OpenMM raises plain Exception/ValueError here
            report.hydrogens_added = False
            report.hydrogenation_error = str(exc)

    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether an OpenMM force field covers every residue in a structure."
    )
    parser.add_argument("structure", type=Path, help="PDB or mmCIF file")
    parser.add_argument(
        "forcefield",
        nargs="+",
        help="Force-field XML file(s), e.g. amber19-all.xml amber19/tip3pfb.xml",
    )
    parser.add_argument(
        "--try-hydrogens",
        action="store_true",
        help="try Modeller.addHydrogens on an in-memory copy and re-check",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=25,
        help="maximum number of individual issues to print (default: 25)",
    )
    args = parser.parse_args(argv)

    report = check_forcefield_coverage(
        args.structure, args.forcefield, try_hydrogens=args.try_hydrogens
    )
    print(report.format(max_details=args.max_details))

    if report.fully_covered:
        return 0
    if report.covered_after_preprocessing:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
