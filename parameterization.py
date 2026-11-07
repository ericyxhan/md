#!/usr/bin/env python3
"""Run ``prepare_system.py`` in its separate CPU parameterization environment.

The simulation environment deliberately does not import OpenFF, RDKit, gemmi,
or PDBFixer.  This module is the only place that crosses that boundary: it
builds the parameterizer command line, runs it as a subprocess, and records a
fingerprint so an existing prepared system can be reused safely.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import ConfigError, WorkflowConfig
from download_file import download_file
from output_bundle import OutputBundle

PROJECT_ROOT = Path(__file__).resolve().parent

COMPLEX_SUFFIXES = {".pdb", ".cif", ".mmcif"}
LIGAND_SUFFIXES = {".sdf", ".sd", ".mol", ".mol2", ".pdb", ".cif", ".mmcif"}


@dataclass(frozen=True)
class InputFiles:
    """Input structures after they have been copied into the output bundle."""

    kind: str
    complex_path: Path | None = None
    protein_path: Path | None = None
    ligand_paths: tuple[Path, ...] = ()

    @property
    def all_paths(self) -> tuple[Path, ...]:
        if self.complex_path is not None:
            return (self.complex_path,)
        paths: list[Path] = []
        if self.protein_path is not None:
            paths.append(self.protein_path)
        paths.extend(self.ligand_paths)
        return tuple(paths)

    def describe(self) -> str:
        if self.complex_path is not None:
            return f"complex file: {self.complex_path}"
        if self.protein_path is not None:
            ligands = ", ".join(str(path) for path in self.ligand_paths)
            return f"protein: {self.protein_path}; ligands: {ligands or 'none'}"
        return "no input files"


@dataclass(frozen=True)
class ParameterizationResult:
    """Paths to the prepared topology and the serialized OpenMM System."""

    prepared_pdb: Path
    system_xml: Path


def _log(message: str) -> None:
    print(message, flush=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_file(path: Path, suffixes: set[str], label: str) -> Path:
    if not path.is_file():
        raise ConfigError(f"{label} not found: {path}")
    if path.suffix.lower() not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise ConfigError(
            f"{label} has unsupported format {path.suffix!r}: {path} "
            f"(supported: {allowed})"
        )
    return path


def _locate_input(
    path: Path,
    suffixes: set[str],
    label: str,
    bundle: OutputBundle,
) -> Path:
    """Use the original input when present, otherwise a bundle copy.

    Falling back to the bundle copy lets an interrupted run resume after the
    user has moved or renamed the original input file.
    """
    if path.is_file():
        return _require_file(path, suffixes, label)
    bundled = bundle.inputs / path.name
    if bundled.is_file():
        _log(f"Warning: {label.lower()} {path} is missing; using {bundled}")
        return _require_file(bundled, suffixes, label)
    raise ConfigError(f"{label} not found: {path}")


def resolve_inputs(config: WorkflowConfig, bundle: OutputBundle) -> InputFiles:
    """Locate inputs, download a PDB ID if needed, and copy them into the bundle."""
    input_config = config.input

    if input_config.pdb_id is not None:
        target = bundle.inputs / f"{input_config.pdb_id}.pdb"
        if not target.is_file():
            url = f"https://files.rcsb.org/download/{input_config.pdb_id}.pdb"
            _log(f"Downloading {url}")
            download_file(url, bundle.inputs)
        if not target.is_file():
            raise RuntimeError(
                f"Download did not produce the expected file: {target}"
            )
        return InputFiles(kind="complex", complex_path=target)

    if input_config.complex_path is not None:
        source = _locate_input(
            input_config.complex_path, COMPLEX_SUFFIXES, "Complex input", bundle
        )
        return InputFiles(kind="complex", complex_path=bundle.copy_input(source))

    assert input_config.protein_path is not None  # validated by InputConfig
    protein = _locate_input(
        input_config.protein_path, COMPLEX_SUFFIXES, "Protein input", bundle
    )
    ligand_paths = tuple(
        bundle.copy_input(
            _locate_input(path, LIGAND_SUFFIXES, "Ligand input", bundle)
        )
        for path in input_config.ligand_paths
    )
    return InputFiles(
        kind="protein+ligands",
        protein_path=bundle.copy_input(protein),
        ligand_paths=ligand_paths,
    )


def parameterizer_python(config: WorkflowConfig) -> Path:
    """Return the interpreter that can import the OpenFF parameterization stack."""
    configured = config.parameterization.python
    if configured is not None:
        candidate = configured
    else:
        environment_value = os.environ.get("OPENMM_PARAMETERIZER_PYTHON")
        if environment_value:
            candidate = Path(environment_value).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
        else:
            candidate = PROJECT_ROOT / ".param-env" / "bin" / "python"

    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise ConfigError(
            f"Parameterizer Python not found: {candidate}\n"
            "Create the CPU parameterization environment with "
            "./create_param_env.sh, or set parameterization.python in "
            "config.toml or OPENMM_PARAMETERIZER_PYTHON."
        )
    return candidate


def build_parameterizer_command(
    config: WorkflowConfig,
    input_files: InputFiles,
    output_dir: Path,
) -> list[str]:
    """Build the exact command used to create the prepared system."""
    settings = config.parameterization
    script = PROJECT_ROOT / "prepare_system.py"
    if not script.is_file():
        raise ConfigError(f"Parameterizer script not found: {script}")

    command = [
        str(parameterizer_python(config)),
        str(script),
        "--output-dir",
        str(output_dir),
        "--ligand-forcefield",
        settings.ligand_forcefield,
        "--ph",
        str(settings.ph),
        "--padding-nm",
        str(settings.padding_nm),
        "--ionic-strength-molar",
        str(settings.ionic_strength_molar),
        "--max-ligand-residues",
        str(settings.max_ligand_residues),
        "--ccd-cache",
        str(settings.ccd_cache),
    ]

    if input_files.complex_path is not None:
        command.extend(["--complex", str(input_files.complex_path)])
    else:
        assert input_files.protein_path is not None
        command.extend(["--protein", str(input_files.protein_path)])
        for ligand_path in input_files.ligand_paths:
            command.extend(["--ligand", str(ligand_path)])

    for forcefield in settings.forcefields:
        command.extend(["--forcefield", forcefield])

    if settings.add_missing_residues:
        command.append("--add-missing-residues")
    if settings.allow_undefined_stereo:
        command.append("--allow-undefined-stereo")

    return command


def _hash_file(path: Path, digest: Any) -> None:
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)


def parameterization_fingerprint(
    config: WorkflowConfig,
    input_files: InputFiles,
) -> str:
    """Hash the inputs and chemistry settings that define the prepared system."""
    settings = config.parameterization
    digest = hashlib.sha256()

    for path in input_files.all_paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        _hash_file(path, digest)
        digest.update(b"\0")

    chemistry = {
        "kind": input_files.kind,
        "forcefields": list(settings.forcefields),
        "ligand_forcefield": settings.ligand_forcefield,
        "ph": settings.ph,
        "padding_nm": settings.padding_nm,
        "ionic_strength_molar": settings.ionic_strength_molar,
        "add_missing_residues": settings.add_missing_residues,
        "allow_undefined_stereo": settings.allow_undefined_stereo,
        "max_ligand_residues": settings.max_ligand_residues,
    }
    digest.update(json.dumps(chemistry, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _manifest(
    config: WorkflowConfig,
    input_files: InputFiles,
    fingerprint: str,
) -> dict[str, object]:
    settings = config.parameterization
    return {
        "fingerprint": fingerprint,
        "created_at": _utc_now(),
        "input_kind": input_files.kind,
        "inputs": [str(path) for path in input_files.all_paths],
        "settings": {
            "forcefields": list(settings.forcefields),
            "ligand_forcefield": settings.ligand_forcefield,
            "ph": settings.ph,
            "padding_nm": settings.padding_nm,
            "ionic_strength_molar": settings.ionic_strength_molar,
            "add_missing_residues": settings.add_missing_residues,
            "allow_undefined_stereo": settings.allow_undefined_stereo,
            "max_ligand_residues": settings.max_ligand_residues,
        },
        "outputs": {
            "prepared_pdb": "metadata/prepared.pdb",
            "system_xml": "metadata/system.xml",
            "report": "metadata/parameterization.txt",
        },
    }


def _clear_parameterization(bundle: OutputBundle) -> None:
    """Remove a prepared system and all stages that depended on it."""
    for name in (
        "prepared.pdb",
        "system.xml",
        "parameterization.txt",
        "parameterization.json",
    ):
        (bundle.metadata / name).unlink(missing_ok=True)
    (bundle.logs / "parameterization.txt").unlink(missing_ok=True)
    bundle.clear_stages()


def _copy_report_to_logs(bundle: OutputBundle, report: Path) -> None:
    bundle.write_text("logs/parameterization.txt", report.read_text(encoding="utf-8"))


def ensure_parameterized(
    config: WorkflowConfig,
    bundle: OutputBundle,
    input_files: InputFiles,
    *,
    force: bool = False,
) -> ParameterizationResult:
    """Reuse a matching prepared system, or run the parameterizer."""
    prepared_pdb = bundle.metadata / "prepared.pdb"
    system_xml = bundle.metadata / "system.xml"
    report = bundle.metadata / "parameterization.txt"
    outputs_exist = all(path.is_file() for path in (prepared_pdb, system_xml, report))

    fingerprint = parameterization_fingerprint(config, input_files)
    try:
        manifest = bundle.read_json("metadata/parameterization.json")
    except json.JSONDecodeError as exc:
        raise ConfigError(
            "The existing parameterization manifest is not valid JSON. "
            "Run with --reparameterize to rebuild the prepared system."
        ) from exc
    if manifest is not None and not isinstance(manifest, dict):
        raise ConfigError(
            "The existing parameterization manifest is not a JSON object. "
            "Run with --reparameterize to rebuild the prepared system."
        )
    reuse_allowed = config.parameterization.reuse_existing and not force

    if reuse_allowed and outputs_exist:
        if manifest is None:
            _log(
                "Warning: existing parameterization has no manifest; "
                "reusing it and recording the current fingerprint."
            )
            bundle.write_json(
                "metadata/parameterization.json",
                _manifest(config, input_files, fingerprint),
            )
        elif manifest.get("fingerprint") != fingerprint:
            raise ConfigError(
                "An existing prepared system was created with different inputs "
                "or parameterization settings.\n"
                "Run again with --reparameterize to rebuild it (this also "
                "clears all simulation stages), or restore the original "
                "configuration."
            )

        _copy_report_to_logs(bundle, report)
        _log(f"Reusing prepared system ({prepared_pdb})")
        return ParameterizationResult(
            prepared_pdb=prepared_pdb,
            system_xml=system_xml,
        )

    _clear_parameterization(bundle)
    command = build_parameterizer_command(config, input_files, bundle.metadata)
    _log("Parameterizing the input in the CPU environment")
    _log("Command: " + shlex.join(command))

    try:
        subprocess.run(command, check=True, cwd=PROJECT_ROOT)
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Could not run the parameterizer Python: {command[0]}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Parameterization failed with exit code {exc.returncode}. "
            "See the parameterizer output above."
        ) from exc

    missing = [
        path for path in (prepared_pdb, system_xml, report) if not path.is_file()
    ]
    if missing:
        raise RuntimeError(
            "Parameterization finished but did not produce: "
            + ", ".join(str(path) for path in missing)
        )

    bundle.write_json(
        "metadata/parameterization.json",
        _manifest(config, input_files, fingerprint),
    )
    _copy_report_to_logs(bundle, report)

    return ParameterizationResult(
        prepared_pdb=prepared_pdb,
        system_xml=system_xml,
    )
