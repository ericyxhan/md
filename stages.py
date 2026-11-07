#!/usr/bin/env python3
"""Create, run, checkpoint, and resume OpenMM simulation stages.

A stage is one integrator run: minimization is handled separately, then any
number of equilibration stages, then an optional production stage.  Each stage
owns a directory::

    stages/<name>/
      checkpoint.chk   exact OpenMM checkpoint for resuming this stage
      state.xml        portable hand-off state for the next stage
      trajectory.dcd   coordinates
      simulation.log   CSV state log
      stage.json       status, fingerprint, timings, final energies

The checkpoint is used only to resume the *same* stage.  The next stage starts
from ``state.xml`` so it can change integrator or barostat settings without
needing a bitwise-compatible checkpoint.  That is why equilibration can switch
from NVT to NPT, and why production can follow either one.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from sys import stdout
from typing import Any, Mapping

from openmm import (
    BrownianIntegrator,
    LangevinIntegrator,
    LangevinMiddleIntegrator,
    MonteCarloBarostat,
    NoseHooverIntegrator,
    Platform,
    System,
    VariableLangevinIntegrator,
    VariableVerletIntegrator,
    VerletIntegrator,
)
from openmm.app import (
    CheckpointReporter,
    DCDReporter,
    PDBFile,
    Simulation,
    StateDataReporter,
    Topology,
)
from openmm.unit import (
    bar,
    kelvin,
    kilojoules_per_mole,
    nanometer,
    picosecond,
    picoseconds,
)

from config import (
    BarostatConfig,
    IntegratorConfig,
    MinimizationConfig,
    StageConfig,
)


def log(message: str) -> None:
    """Print a pipeline message with a wall-clock timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Integrators and barostats
# ---------------------------------------------------------------------------


def create_integrator(config: IntegratorConfig) -> Any:
    """Build the OpenMM integrator described by *config*."""
    temperature = (config.temperature_k or 300.0) * kelvin
    friction = (config.friction_per_ps or 1.0) / picosecond
    timestep = (config.timestep_ps or 0.002) * picoseconds

    if config.type == "langevin_middle":
        integrator = LangevinMiddleIntegrator(temperature, friction, timestep)
    elif config.type == "langevin":
        integrator = LangevinIntegrator(temperature, friction, timestep)
    elif config.type == "brownian":
        integrator = BrownianIntegrator(temperature, friction, timestep)
    elif config.type == "verlet":
        integrator = VerletIntegrator(timestep)
    elif config.type == "variable_verlet":
        integrator = VariableVerletIntegrator(config.error_tolerance or 0.001)
    elif config.type == "variable_langevin":
        integrator = VariableLangevinIntegrator(
            temperature,
            friction,
            config.error_tolerance or 0.001,
        )
    elif config.type == "nose_hoover":
        integrator = NoseHooverIntegrator(
            temperature,
            (config.collision_frequency_per_ps or 1.0) / picosecond,
            timestep,
        )
    else:  # pragma: no cover - config validation catches this first
        raise ValueError(f"Unsupported integrator type: {config.type}")

    if config.constraint_tolerance is not None:
        integrator.setConstraintTolerance(config.constraint_tolerance)
    if config.integration_force_groups is not None:
        integrator.setIntegrationForceGroups(config.integration_force_groups)
    if config.random_seed is not None and hasattr(
        integrator, "setRandomNumberSeed"
    ):
        integrator.setRandomNumberSeed(config.random_seed)
    if config.maximum_step_ps is not None and hasattr(
        integrator, "setMaximumStepSize"
    ):
        integrator.setMaximumStepSize(config.maximum_step_ps * picoseconds)

    return integrator


def add_barostat(system: System, config: BarostatConfig) -> None:
    """Add pressure control to *system* when the stage asks for it."""
    if config.type == "none":
        return
    if not system.usesPeriodicBoundaryConditions():
        raise RuntimeError(
            "A barostat requires a periodic system, but the prepared System "
            "does not define periodic box vectors."
        )
    for force in system.getForces():
        if isinstance(force, MonteCarloBarostat):
            raise RuntimeError(
                "The prepared System already contains a MonteCarloBarostat; "
                "remove it from system.xml before configuring one here."
            )

    barostat = MonteCarloBarostat(
        config.pressure_bar * bar,
        (config.temperature_k or 300.0) * kelvin,
        config.frequency,
    )
    if config.random_seed is not None:
        barostat.setRandomNumberSeed(config.random_seed)
    system.addForce(barostat)


def _create_simulation(
    system: System,
    topology: Topology,
    stage: StageConfig,
    platform: Platform,
    platform_properties: Mapping[str, str],
) -> Simulation:
    """Create a fresh Simulation so retries cannot inherit a broken Context."""
    stage_system = copy.deepcopy(system)
    add_barostat(stage_system, stage.barostat)
    integrator = create_integrator(stage.integrator)
    return Simulation(
        topology,
        stage_system,
        integrator,
        platform,
        dict(platform_properties),
    )


# ---------------------------------------------------------------------------
# Stage fingerprints and completion state
# ---------------------------------------------------------------------------


def stage_fingerprint(stage: StageConfig) -> str:
    """Hash only settings that make a checkpoint unsafe to reuse.

    Step count, report intervals, and retry counts are intentionally excluded:
    a user can extend production, change logging frequency, or add retries
    without throwing away an existing checkpoint.
    """
    payload = {
        "integrator": asdict(stage.integrator),
        "barostat": asdict(stage.barostat),
    }
    serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def read_manifest(path: Path) -> dict[str, Any] | None:
    """Read a stage manifest, treating a corrupt file as missing."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log(f"Warning: could not read {path}; treating it as missing.")
        return None
    return data if isinstance(data, dict) else None


def _write_manifest(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _fingerprint_error(stage: StageConfig) -> RuntimeError:
    return RuntimeError(
        f"Stage {stage.name!r} was created with a different integrator or "
        "barostat, so its checkpoint cannot be reused safely.\n"
        f"Run again with --restart-stage {stage.name} to start this stage "
        "from the previous stage's state."
    )


def stage_completed(stage_dir: Path, stage: StageConfig) -> bool:
    """Return True only when this exact stage has finished its current target."""
    stage_dir = Path(stage_dir)
    manifest = read_manifest(stage_dir / "stage.json")
    if manifest is None:
        return False

    if manifest.get("config_fingerprint") != stage_fingerprint(stage):
        raise _fingerprint_error(stage)

    if manifest.get("status") != "completed":
        return False

    state_path = stage_dir / "state.xml"
    if not state_path.is_file():
        raise RuntimeError(
            f"Stage {stage.name!r} is marked complete but {state_path} is "
            f"missing. Run again with --restart-stage {stage.name}."
        )

    completed_steps = int(manifest.get("steps_completed", 0))
    return completed_steps >= stage.steps


# ---------------------------------------------------------------------------
# Small state helpers
# ---------------------------------------------------------------------------


def _state_is_finite(simulation: Simulation) -> bool:
    """Check for NaN/inf before resuming from a checkpoint."""
    state = simulation.context.getState(getEnergy=True)
    potential = state.getPotentialEnergy().value_in_unit(kilojoules_per_mole)
    kinetic = state.getKineticEnergy().value_in_unit(kilojoules_per_mole)
    return math.isfinite(potential) and math.isfinite(kinetic)


def _quarantine_checkpoint(path: Path) -> Path:
    """Move an unusable checkpoint aside so a retry can start cleanly."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.unusable-{stamp}")
    counter = 1
    while target.exists():
        counter += 1
        target = path.with_name(f"{path.name}.unusable-{stamp}-{counter}")
    path.replace(target)
    return target


def _clear_stage_outputs(stage_dir: Path) -> None:
    for name in (
        "checkpoint.chk",
        "trajectory.dcd",
        "simulation.log",
        "state.xml",
        "stage.json",
    ):
        (stage_dir / name).unlink(missing_ok=True)


def _set_velocities(simulation: Simulation, stage: StageConfig) -> None:
    temperature = stage.velocity_temperature_k * kelvin
    if stage.velocity_seed is None:
        simulation.context.setVelocitiesToTemperature(temperature)
    else:
        simulation.context.setVelocitiesToTemperature(
            temperature, stage.velocity_seed
        )


def _load_initial_state(
    simulation: Simulation,
    *,
    stage: StageConfig,
    initial_state_path: Path | None,
    positions: Any,
    box_vectors: Any | None,
    reset_velocities: bool,
) -> None:
    """Start a stage from the previous stage's state or from fresh coordinates."""
    if initial_state_path is not None and Path(initial_state_path).is_file():
        try:
            simulation.loadState(str(initial_state_path))
        except Exception as exc:
            raise RuntimeError(
                f"Could not load the hand-off state {initial_state_path} for "
                f"stage {stage.name!r}. The upstream state may be corrupt or "
                "incompatible; rerun with --restart to rebuild the simulation "
                "stages, or with --reparameterize if the prepared system "
                "changed."
            ) from exc
        # Stage progress is local, even though simulation time is cumulative.
        simulation.currentStep = 0
        if reset_velocities:
            _set_velocities(simulation, stage)
        return

    simulation.context.setPositions(positions)
    if box_vectors is not None:
        simulation.context.setPeriodicBoxVectors(*box_vectors)
    simulation.currentStep = 0
    _set_velocities(simulation, stage)


def _add_reporters(
    simulation: Simulation,
    stage: StageConfig,
    *,
    trajectory_path: Path,
    state_log_path: Path,
    checkpoint_path: Path,
    resumed: bool,
) -> None:
    periodic = simulation.system.usesPeriodicBoundaryConditions()
    trajectory_interval = stage.trajectory_report_interval

    if trajectory_interval is not None:
        simulation.reporters.append(
            DCDReporter(
                str(trajectory_path),
                trajectory_interval,
                append=resumed and trajectory_path.is_file(),
            )
        )

    reporter_fields = {
        "step": True,
        "time": True,
        "potentialEnergy": True,
        "kineticEnergy": True,
        "temperature": True,
        "volume": periodic,
        "density": periodic,
        "speed": True,
        "progress": True,
        "remainingTime": True,
        "elapsedTime": True,
        "totalSteps": stage.steps,
    }
    simulation.reporters.append(
        StateDataReporter(stdout, stage.report_interval, **reporter_fields)
    )
    simulation.reporters.append(
        StateDataReporter(
            str(state_log_path),
            stage.report_interval,
            append=resumed and state_log_path.is_file(),
            **reporter_fields,
        )
    )
    simulation.reporters.append(
        CheckpointReporter(str(checkpoint_path), stage.checkpoint_interval)
    )


# ---------------------------------------------------------------------------
# Public stage runner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageResult:
    """What a completed stage produced."""

    stage: StageConfig
    stage_dir: Path
    checkpoint_path: Path
    state_path: Path
    steps_completed: int
    resumed: bool
    duration_s: float


def run_stage(
    *,
    system: System,
    topology: Topology,
    positions: Any,
    box_vectors: Any | None,
    stage: StageConfig,
    stage_dir: Path,
    platform: Platform,
    platform_properties: Mapping[str, str] | None = None,
    initial_state_path: Path | None = None,
    resume: bool = True,
    reset_velocities: bool = False,
) -> StageResult:
    """Run one stage, resuming and retrying from its checkpoint as needed.

    ``resume=False`` discards this stage's own checkpoint and outputs before
    the first attempt.  Later attempts still resume from any checkpoint that
    the failed attempt managed to write, which is what makes retries useful.
    """
    stage.validate(f"stage {stage.name!r}")
    stage_dir = Path(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    if not resume:
        _clear_stage_outputs(stage_dir)

    checkpoint_path = stage_dir / "checkpoint.chk"
    state_path = stage_dir / "state.xml"
    manifest_path = stage_dir / "stage.json"
    fingerprint = stage_fingerprint(stage)

    existing_manifest = read_manifest(manifest_path)
    if (
        existing_manifest is not None
        and existing_manifest.get("config_fingerprint") != fingerprint
    ):
        raise _fingerprint_error(stage)

    properties = dict(platform_properties or {})
    last_error: Exception | None = None

    for attempt in range(stage.retries + 1):
        try:
            return _run_stage_attempt(
                system=system,
                topology=topology,
                positions=positions,
                box_vectors=box_vectors,
                stage=stage,
                stage_dir=stage_dir,
                platform=platform,
                platform_properties=properties,
                initial_state_path=initial_state_path,
                checkpoint_path=checkpoint_path,
                state_path=state_path,
                manifest_path=manifest_path,
                fingerprint=fingerprint,
                previous_manifest=existing_manifest,
                attempt=attempt + 1,
                reset_velocities=reset_velocities,
            )
        except Exception as exc:  # noqa: BLE001 - retries are the point
            last_error = exc
            if attempt >= stage.retries:
                break
            log(
                f"Stage {stage.name!r} attempt {attempt + 1} failed: {exc}"
            )
            log(
                f"Retrying in {stage.retry_delay_s:g} s; the latest usable "
                f"checkpoint will be used if present..."
            )
            time.sleep(stage.retry_delay_s)

    assert last_error is not None
    raise last_error


def _run_stage_attempt(
    *,
    system: System,
    topology: Topology,
    positions: Any,
    box_vectors: Any | None,
    stage: StageConfig,
    stage_dir: Path,
    platform: Platform,
    platform_properties: Mapping[str, str],
    initial_state_path: Path | None,
    checkpoint_path: Path,
    state_path: Path,
    manifest_path: Path,
    fingerprint: str,
    previous_manifest: dict[str, Any] | None,
    attempt: int,
    reset_velocities: bool,
) -> StageResult:
    simulation = _create_simulation(
        system, topology, stage, platform, platform_properties
    )
    resumed = False

    if checkpoint_path.is_file():
        try:
            simulation.loadCheckpoint(str(checkpoint_path))
            if not _state_is_finite(simulation):
                raise RuntimeError("checkpoint contains non-finite energy")
        except Exception as exc:
            backup = _quarantine_checkpoint(checkpoint_path)
            log(
                f"Stage {stage.name!r}: checkpoint was unusable ({exc}); "
                f"moved it to {backup.name} and restarting from the stage input."
            )
            simulation = _create_simulation(
                system, topology, stage, platform, platform_properties
            )
            resumed = False
        else:
            resumed = True

    if not resumed:
        _load_initial_state(
            simulation,
            stage=stage,
            initial_state_path=initial_state_path,
            positions=positions,
            box_vectors=box_vectors,
            reset_velocities=reset_velocities,
        )
        if not _state_is_finite(simulation):
            raise RuntimeError(
                f"Stage {stage.name!r} received a non-finite starting state. "
                "Rerun minimization or restart from a good checkpoint."
            )

    start_step = simulation.currentStep
    if start_step > stage.steps:
        log(
            f"Stage {stage.name!r}: checkpoint is already at step "
            f"{start_step}, beyond the configured {stage.steps}; "
            "finishing without running more steps."
        )

    started_at = (
        previous_manifest.get("started_at")
        if previous_manifest is not None
        else _utc_now()
    )
    _write_manifest(
        manifest_path,
        {
            "name": stage.name,
            "status": "running",
            "config_fingerprint": fingerprint,
            "started_at": started_at,
            "updated_at": _utc_now(),
            "attempt": attempt,
            "start_step": start_step,
            "target_steps": stage.steps,
            "resumed": resumed,
            "integrator": asdict(stage.integrator),
            "barostat": asdict(stage.barostat),
        },
    )

    started = time.monotonic()
    try:
        if start_step < stage.steps:
            _add_reporters(
                simulation,
                stage,
                trajectory_path=stage_dir / "trajectory.dcd",
                state_log_path=stage_dir / "simulation.log",
                checkpoint_path=checkpoint_path,
                resumed=resumed,
            )
            simulation.step(stage.steps - start_step)
            if not _state_is_finite(simulation):
                raise RuntimeError(
                    f"Stage {stage.name!r} produced a non-finite energy; "
                    "the run will retry from the latest usable checkpoint."
                )

        simulation.saveCheckpoint(str(checkpoint_path))
        simulation.saveState(str(state_path))
    except Exception as exc:
        _write_manifest(
            manifest_path,
            {
                "name": stage.name,
                "status": "failed",
                "config_fingerprint": fingerprint,
                "started_at": started_at,
                "updated_at": _utc_now(),
                "attempt": attempt,
                "start_step": start_step,
                "target_steps": stage.steps,
                "resumed": resumed,
                "error": str(exc),
                "integrator": asdict(stage.integrator),
                "barostat": asdict(stage.barostat),
            },
        )
        raise

    duration_s = time.monotonic() - started
    steps_completed = simulation.currentStep
    state = simulation.context.getState(getEnergy=True)
    potential_energy = state.getPotentialEnergy().value_in_unit(
        kilojoules_per_mole
    )

    _write_manifest(
        manifest_path,
        {
            "name": stage.name,
            "status": "completed",
            "config_fingerprint": fingerprint,
            "started_at": started_at,
            "completed_at": _utc_now(),
            "attempt": attempt,
            "steps_completed": steps_completed,
            "configured_steps": stage.steps,
            "resumed": resumed,
            "duration_s": round(duration_s, 3),
            "potential_energy_kj_mol": round(potential_energy, 6),
            "checkpoint": checkpoint_path.name,
            "state": state_path.name,
            "trajectory": (
                "trajectory.dcd"
                if stage.trajectory_report_interval is not None
                else None
            ),
            "state_log": "simulation.log",
            "integrator": asdict(stage.integrator),
            "barostat": asdict(stage.barostat),
        },
    )

    log(
        f"Stage {stage.name!r} complete: {steps_completed} steps in "
        f"{duration_s:.1f} s"
    )
    return StageResult(
        stage=stage,
        stage_dir=stage_dir,
        checkpoint_path=checkpoint_path,
        state_path=state_path,
        steps_completed=steps_completed,
        resumed=resumed,
        duration_s=duration_s,
    )


# ---------------------------------------------------------------------------
# Minimization
# ---------------------------------------------------------------------------


def run_minimization(
    *,
    system: System,
    topology: Topology,
    positions: Any,
    box_vectors: Any | None,
    output_dir: Path,
    platform: Platform,
    platform_properties: Mapping[str, str] | None = None,
    config: MinimizationConfig,
) -> Path:
    """Minimize the prepared coordinates and write a hand-off state."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "state.xml"

    simulation = Simulation(
        topology,
        copy.deepcopy(system),
        VerletIntegrator(0.001 * picoseconds),
        platform,
        dict(platform_properties or {}),
    )
    simulation.context.setPositions(positions)
    if box_vectors is not None:
        simulation.context.setPeriodicBoxVectors(*box_vectors)

    started_at = _utc_now()
    initial_state = simulation.context.getState(getEnergy=True)
    initial_energy = initial_state.getPotentialEnergy().value_in_unit(
        kilojoules_per_mole
    )

    log(
        f"Minimizing energy (max_iterations={config.max_iterations}, "
        f"tolerance={config.tolerance_kj_mol_nm:g} kJ/mol/nm)"
    )
    simulation.minimizeEnergy(
        tolerance=config.tolerance_kj_mol_nm * kilojoules_per_mole / nanometer,
        maxIterations=config.max_iterations,
    )

    final_state = simulation.context.getState(getPositions=True, getEnergy=True)
    final_energy = final_state.getPotentialEnergy().value_in_unit(
        kilojoules_per_mole
    )
    if not math.isfinite(final_energy):
        raise RuntimeError(
            "Minimization produced a non-finite potential energy. "
            "Check the prepared system and input coordinates."
        )
    simulation.saveState(str(state_path))

    with (output_dir / "minimized.pdb").open("w", encoding="utf-8") as handle:
        PDBFile.writeFile(
            topology,
            final_state.getPositions(),
            handle,
            keepIds=True,
        )

    report = (
        "Energy minimization\n"
        "===================\n"
        f"Max iterations: {config.max_iterations}\n"
        f"Tolerance: {config.tolerance_kj_mol_nm:g} kJ/mol/nm\n"
        f"Initial potential energy: {initial_energy:.3f} kJ/mol\n"
        f"Final potential energy: {final_energy:.3f} kJ/mol\n"
        f"State: {state_path.name}\n"
    )
    (output_dir / "minimization.log").write_text(report, encoding="utf-8")
    _write_manifest(
        output_dir / "stage.json",
        {
            "name": "minimization",
            "status": "completed",
            "started_at": started_at,
            "completed_at": _utc_now(),
            "steps_completed": 0,
            "initial_potential_energy_kj_mol": round(initial_energy, 6),
            "final_potential_energy_kj_mol": round(final_energy, 6),
            "state": state_path.name,
        },
    )

    log(
        f"Minimization complete: {initial_energy:.1f} -> "
        f"{final_energy:.1f} kJ/mol"
    )
    return state_path
