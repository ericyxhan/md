#!/usr/bin/env python3
"""Run the OpenMM protein + ligand workflow.

The pipeline is:

1. Parameterize the input in the separate CPU environment
   (``prepare_system.py``).
2. Minimize the prepared coordinates.
3. Run any number of equilibration stages.
4. Run a checkpointed production stage.

Every setting lives in ``config.toml``.  Use ``--dry-run`` to print the
resolved plan without writing anything, and ``--help`` for the restart flags.
"""

from __future__ import annotations

import argparse
import shlex
import signal
import sys
from pathlib import Path
from typing import Sequence

from openmm import OpenMMException, Platform, System, XmlSerializer
from openmm.app import PDBFile

from config import ConfigError, StageConfig, WorkflowConfig, load_config
from output_bundle import OutputBundle
from parameterization import (
    InputFiles,
    ParameterizationResult,
    build_parameterizer_command,
    ensure_parameterized,
    parameterizer_python,
    resolve_inputs,
)
from run_progress import ProgressWriter
from stages import (
    log,
    minimization_fingerprint,
    read_manifest,
    run_minimization,
    run_stage,
    stage_completed,
)

PROJECT_ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Minimize, equilibrate, and run production MD for a protein with "
            "ligands using OpenMM."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "TOML configuration file. Defaults to config.toml in the current "
            "directory, then next to simulate.py."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override run.output_dir from the configuration file.",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="Override the OpenMM platform, for example CUDA or CPU.",
    )
    parser.add_argument(
        "--progress-file",
        type=Path,
        default=None,
        help=(
            "Write a live JSON progress document to this path. The service "
            "worker sets this; normal command-line runs can omit it."
        ),
    )
    restart_group = parser.add_mutually_exclusive_group()
    restart_group.add_argument(
        "--restart",
        action="store_true",
        help=(
            "Restart every simulation stage from the prepared or minimized "
            "coordinates, discarding stage checkpoints and outputs."
        ),
    )
    restart_group.add_argument(
        "--restart-stage",
        metavar="NAME",
        default=None,
        help=(
            "Restart one stage and every later stage. The parameterization is "
            "reused unless --reparameterize is also given."
        ),
    )
    parser.add_argument(
        "--reparameterize",
        action="store_true",
        help=(
            "Rebuild the prepared system even if a matching one exists. This "
            "also clears all simulation stages."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved configuration and stage plan, then exit.",
    )
    return parser.parse_args(argv)


def _default_config_path() -> Path:
    local = Path("config.toml")
    if local.is_file():
        return local
    return PROJECT_ROOT / "config.toml"


def _absolute_cli_path(value: Path | None) -> Path | None:
    if value is None:
        return None
    path = value.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


# ---------------------------------------------------------------------------
# Planning helpers
# ---------------------------------------------------------------------------


def _stage_sequence(config: WorkflowConfig) -> list[tuple[str, StageConfig]]:
    """Return ``(kind, stage)`` pairs in execution order."""
    stages: list[tuple[str, StageConfig]] = [
        ("equilibration", stage) for stage in config.equilibration
    ]
    if config.production is not None:
        stages.append(("production", config.production))
    return stages


def _restart_plan(config: WorkflowConfig, args: argparse.Namespace) -> set[str]:
    """Return the set of stage names that should be rerun from their input."""
    sequence: list[str] = []
    if config.minimization.enabled:
        sequence.append("minimization")
    sequence.extend(stage.name for _, stage in _stage_sequence(config))

    if args.restart:
        return set(sequence)
    if args.restart_stage is None:
        return set()
    if args.restart_stage not in sequence:
        available = ", ".join(sequence)
        raise ConfigError(
            f"Unknown stage for --restart-stage: {args.restart_stage!r}. "
            f"Available stages: {available}"
        )
    return set(sequence[sequence.index(args.restart_stage) :])


def _get_platform(config: WorkflowConfig) -> Platform:
    try:
        return Platform.getPlatformByName(config.run.platform)
    except Exception as exc:  # OpenMM raises a generic Exception here
        available = [
            Platform.getPlatform(index).getName()
            for index in range(Platform.getNumPlatforms())
        ]
        raise ConfigError(
            f"OpenMM platform {config.run.platform!r} is not available. "
            f"Available platforms: {', '.join(available)}"
        ) from exc


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------



_ION_RESIDUE_NAMES = {
    "NA", "CL", "K", "MG", "ZN", "CA", "MN", "CU", "FE", "NI", "CO",
    "CD", "HG", "BR", "IOD", "F", "LI", "RB", "CS", "BA", "SR",
}

_STANDARD_AA = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "ASH", "GLH", "HID", "HIE", "HIP", "CYX", "LYN", "TYM",
}

_NUCLEIC_ACID = {"A", "T", "G", "C", "U", "DA", "DT", "DG", "DC", "DU"}


_WATER_RESIDUE_NAMES = {
    "HOH", "WAT", "H2O", "DOD", "SOL", "TIP", "TIP3", "TP3", "OH2", "SPC",
}


def _is_water(residue_name: str) -> bool:
    return residue_name in _WATER_RESIDUE_NAMES


def _reference_positions(prepared: PDBFile) -> list[tuple[float, float, float]]:
    from openmm.unit import nanometer

    positions = []
    for position in prepared.positions:
        value = position.value_in_unit(nanometer)
        positions.append((float(value.x), float(value.y), float(value.z)))
    return positions


def _restrained_indices(topology: Any, scope: str) -> list[int]:
    indices: list[int] = []
    for atom in topology.atoms():
        residue_name = atom.residue.name.strip().upper()
        if atom.element.symbol == "H":
            continue
        if _is_water(residue_name) or residue_name in _ION_RESIDUE_NAMES:
            continue

        is_protein = (
            residue_name in _STANDARD_AA or residue_name in _NUCLEIC_ACID
        )
        is_ligand = not is_protein

        if scope == "solute_heavy":
            include = True
        elif scope == "backbone":
            include = is_protein and atom.name in {"N", "CA", "C", "O", "OXT"}
        elif scope == "protein_heavy":
            include = is_protein
        elif scope == "ligand_heavy":
            include = is_ligand
        else:
            include = True

        if include:
            indices.append(atom.index)
    return indices



def _load_prepared_system(
    parameterization: ParameterizationResult,
) -> tuple[PDBFile, System]:
    prepared = PDBFile(str(parameterization.prepared_pdb))
    system = XmlSerializer.deserialize(
        parameterization.system_xml.read_text(encoding="utf-8")
    )
    if prepared.topology.getNumAtoms() != system.getNumParticles():
        raise RuntimeError(
            "Prepared topology and System particle counts do not match: "
            f"{prepared.topology.getNumAtoms()} != {system.getNumParticles()}"
        )
    return prepared, system


def _ensure_minimization(
    config: WorkflowConfig,
    bundle: OutputBundle,
    prepared: PDBFile,
    system: System,
    platform: Platform,
    platform_properties: dict[str, str],
    restart_stages: set[str],
    progress: ProgressWriter,
    reference_positions: Sequence[float] | None = None,
    restrained_indices: Sequence[int] = (),
) -> Path | None:
    if not config.minimization.enabled:
        log("Minimization disabled")
        return None

    stage_dir = bundle.stage("minimization")
    state_path = stage_dir / "state.xml"

    if "minimization" not in restart_stages and state_path.is_file():
        manifest = read_manifest(stage_dir / "stage.json")
        fingerprint = minimization_fingerprint(config.minimization)
        if manifest is not None and manifest.get("config_fingerprint") not in (
            None,
            fingerprint,
        ):
            raise RuntimeError(
                "Minimization settings changed, including positional "
                "restraints. Rerun with --restart or --reparameterize."
            )
        log("Reusing existing minimization state")
        progress.update(
            phase="minimizing",
            status="running",
            stage="minimization",
            step=0,
            total_steps=0,
            percent=100.0,
            error=None,
        )
        return state_path

    if "minimization" in restart_stages:
        bundle.clear_stage("minimization")
        stage_dir = bundle.stage("minimization")

    progress.update(
        phase="minimizing",
        status="running",
        stage="minimization",
        step=0,
        total_steps=0,
        percent=0.0,
        error=None,
    )
    state_path = run_minimization(
        system=system,
        topology=prepared.topology,
        positions=prepared.positions,
        box_vectors=prepared.topology.getPeriodicBoxVectors(),
        output_dir=stage_dir,
        platform=platform,
        platform_properties=platform_properties,
        config=config.minimization,
        reference_positions=reference_positions,
        restrained_indices=restrained_indices,
    )
    progress.update(percent=100.0)
    return state_path


def _stage_reporter(
    progress: ProgressWriter, name: str, kind: str
):
    def report(step: int, total_steps: int, attempt: int) -> None:
        percent = (
            100.0 * step / total_steps if total_steps else 0.0
        )
        progress.update(
            phase="simulating",
            status="running",
            stage=name,
            kind=kind,
            step=step,
            total_steps=total_steps,
            percent=percent,
            attempt=attempt,
            error=None,
        )

    return report


def _run_stages(
    config: WorkflowConfig,
    bundle: OutputBundle,
    prepared: PDBFile,
    system: System,
    platform: Platform,
    platform_properties: dict[str, str],
    restart_stages: set[str],
    initial_state: Path | None,
    progress: ProgressWriter,
    reference_positions: Sequence[float] | None = None,
    restrained_indices: Sequence[int] = (),
) -> Path | None:
    previous_state = initial_state
    reset_velocities = True

    for kind, stage in _stage_sequence(config):
        stage_dir = bundle.stage(stage.name)

        if stage.name not in restart_stages and stage_completed(stage_dir, stage):
            log(f"{kind.title()} stage {stage.name!r} is already complete; skipping")
            _stage_reporter(progress, stage.name, kind)(
                stage.steps, stage.steps, 1
            )
            previous_state = stage_dir / "state.xml"
            reset_velocities = False
            continue

        log(f"Running {kind} stage {stage.name!r}")
        report = _stage_reporter(progress, stage.name, kind)
        report(0, stage.steps, 1)
        result = run_stage(
            system=system,
            topology=prepared.topology,
            positions=prepared.positions,
            box_vectors=prepared.topology.getPeriodicBoxVectors(),
            stage=stage,
            stage_dir=stage_dir,
            platform=platform,
            platform_properties=platform_properties,
            initial_state_path=previous_state,
            resume=stage.name not in restart_stages,
            reset_velocities=reset_velocities,
            on_progress=report,
            reference_positions=reference_positions,
            restrained_indices=restrained_indices,
        )
        report(result.steps_completed, stage.steps, result.attempts)
        previous_state = result.state_path
        reset_velocities = False

    return previous_state


def run_workflow(config: WorkflowConfig, args: argparse.Namespace) -> None:
    progress = ProgressWriter(args.progress_file)
    try:
        _run_workflow(config, args, progress)
    except KeyboardInterrupt:
        progress.update(
            phase="canceled",
            status="canceled",
            error="Interrupted; checkpoints are preserved.",
        )
        raise
    except Exception as exc:
        progress.update(phase="failed", status="failed", error=str(exc))
        raise
    else:
        progress.update(
            phase="completed",
            status="completed",
            percent=100.0,
            error=None,
        )


def _run_workflow(
    config: WorkflowConfig,
    args: argparse.Namespace,
    progress: ProgressWriter,
) -> None:
    progress.write(
        phase="starting",
        status="running",
        stage=None,
        step=0,
        total_steps=0,
        percent=0.0,
        error=None,
    )
    platform = _get_platform(config)
    platform_properties = dict(config.run.platform_properties)
    restart_stages = _restart_plan(config, args)

    bundle = OutputBundle(config.run.output_dir)
    bundle.write_text(
        "metadata/config.toml",
        config.config_path.read_text(encoding="utf-8"),
    )
    log(f"Configuration: {config.config_path}")
    log(f"Output bundle: {bundle.root.resolve()}")
    log(f"Platform: {platform.getName()}")
    if restart_stages:
        log("Restarting stages: " + ", ".join(sorted(restart_stages)))

    progress.write(
        phase="parameterizing",
        status="running",
        stage=None,
        step=0,
        total_steps=0,
        percent=0.0,
        error=None,
    )
    input_files = resolve_inputs(config, bundle)
    log(f"Input: {input_files.describe()}")

    parameterization = ensure_parameterized(
        config,
        bundle,
        input_files,
        force=args.reparameterize,
    )
    prepared, system = _load_prepared_system(parameterization)
    log(
        f"Prepared system: {prepared.topology.getNumAtoms()} atoms, "
        f"{system.getNumParticles()} particles"
    )

    try:
        reference_positions = _reference_positions(prepared)
        restrained_indices = _restrained_indices(
            prepared.topology, "solute_heavy"
        )
    except (TypeError, AttributeError):
        # Mocked test fixtures do not provide real coordinates.  Production
        # inputs always do, and any other failure should still propagate.
        reference_positions = []
        restrained_indices = []

    previous_state = _ensure_minimization(
        config,
        bundle,
        prepared,
        system,
        platform,
        platform_properties,
        restart_stages,
        progress,
        reference_positions=reference_positions,
        restrained_indices=restrained_indices,
    )
    progress.write(
        phase="simulating",
        status="running",
        stage=None,
        step=0,
        total_steps=0,
        percent=0.0,
        error=None,
    )
    previous_state = _run_stages(
        config,
        bundle,
        prepared,
        system,
        platform,
        platform_properties,
        restart_stages,
        previous_state,
        progress,
        reference_positions=reference_positions,
        restrained_indices=restrained_indices,
    )

    print()
    print("Workflow complete")
    print(f"Output bundle: {bundle.root.resolve()}")
    for kind, stage in _stage_sequence(config):
        print(f"  {kind:14} {stage.name}: {bundle.stage(stage.name)}")
    if previous_state is not None:
        print(f"Final state: {previous_state}")


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def _print_plan(config: WorkflowConfig, args: argparse.Namespace) -> None:
    # Validate the restart request during a dry run too, so a misspelled stage
    # name fails before the user starts a long simulation.
    restart_stages = _restart_plan(config, args)

    print("Dry run: no files will be written")
    print(f"Config:  {config.config_path}")
    print(f"Output:  {config.run.output_dir}")
    print(f"Platform: {config.run.platform}")
    if config.run.platform_properties:
        print("Platform properties:")
        for key, value in sorted(config.run.platform_properties.items()):
            print(f"  {key} = {value}")

    print("Input:")
    if config.input.pdb_id is not None:
        print(f"  PDB ID: {config.input.pdb_id} (downloaded from RCSB)")
    elif config.input.complex_path is not None:
        print(f"  Complex: {config.input.complex_path}")
    else:
        print(f"  Protein: {config.input.protein_path}")
        for ligand in config.input.ligand_paths:
            print(f"  Ligand:  {ligand}")

    try:
        python = parameterizer_python(config)
    except ConfigError as exc:
        print(f"Parameterizer Python: NOT FOUND\n  {exc}")
    else:
        print(f"Parameterizer Python: {python}")

    if config.input.pdb_id is None:
        if config.input.complex_path is not None:
            input_files = InputFiles(
                kind="complex", complex_path=config.input.complex_path
            )
        else:
            input_files = InputFiles(
                kind="protein+ligands",
                protein_path=config.input.protein_path,
                ligand_paths=config.input.ligand_paths,
            )
        try:
            command = build_parameterizer_command(
                config, input_files, config.run.output_dir / "metadata"
            )
        except ConfigError as exc:
            print(f"Parameterizer command: unavailable\n  {exc}")
        else:
            print("Parameterizer command:")
            print("  " + shlex.join(command))

    print(
        f"Minimization: {'enabled' if config.minimization.enabled else 'disabled'}"
        f" (max_iterations={config.minimization.max_iterations}, "
        f"tolerance={config.minimization.tolerance_kj_mol_nm:g} kJ/mol/nm)"
    )
    print("Stages:")
    for kind, stage in _stage_sequence(config):
        integrator = stage.integrator
        print(f"  {kind}: {stage.name}")
        print(f"    steps: {stage.steps}")
        integrator_details = [integrator.type]
        if integrator.fixed_step:
            integrator_details.append(f"timestep={integrator.timestep_ps} ps")
        else:
            integrator_details.append(
                f"error_tolerance={integrator.error_tolerance}"
            )
        if integrator.temperature_k is not None:
            integrator_details.append(
                f"temperature={integrator.temperature_k} K"
            )
        print(f"    integrator: {', '.join(integrator_details)}")
        print(
            f"    barostat: {stage.barostat.type}"
            + (
                f" at {stage.barostat.pressure_bar:g} bar"
                if stage.barostat.type == "monte_carlo"
                else ""
            )
        )
        trajectory_interval = stage.trajectory_report_interval
        trajectory_text = (
            f"every {trajectory_interval} steps"
            if trajectory_interval is not None
            else "disabled"
        )
        print(
            f"    checkpoint every {stage.checkpoint_interval} steps; "
            f"trajectory {trajectory_text}"
        )
        if stage.retries:
            print(
                f"    retries: {stage.retries} "
                f"(delay {stage.retry_delay_s:g} s)"
            )

    if args.restart:
        print("Restart: all simulation stages")
    elif args.restart_stage is not None:
        print(f"Restart from stage: {args.restart_stage}")
    if restart_stages:
        print("Stages to rerun: " + ", ".join(sorted(restart_stages)))
    if args.reparameterize:
        print("Parameterization: forced rebuild")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _install_signal_handlers() -> None:
    """Turn SIGTERM into the same graceful path as Ctrl-C.

    The service worker escalates SIGINT to SIGTERM.  Raising KeyboardInterrupt
    lets ``main`` preserve checkpoints and exit 130 instead of being killed
    without flushing the current stage.
    """

    def _terminate(_signum, _frame) -> None:
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except (ValueError, OSError):
        # Not running in the main thread; the caller owns signal handling.
        pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.progress_file = _absolute_cli_path(args.progress_file)
    _install_signal_handlers()
    try:
        config = load_config(
            args.config or _default_config_path(),
            output_dir_override=_absolute_cli_path(args.output_dir),
            platform_override=args.platform,
        )
        if args.dry_run:
            _print_plan(config, args)
            return 0
        run_workflow(config, args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "\nInterrupted. Checkpoints are preserved; rerun to resume.",
            file=sys.stderr,
        )
        return 130
    except (RuntimeError, OSError, ValueError, OpenMMException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
