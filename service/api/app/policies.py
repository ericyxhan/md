"""Safe allowlists, limits, and resolved-plan construction.

Nothing here accepts raw TOML, paths, executables, platform properties, or
force-field locations.  The request model is the only user-controlled input.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .errors import APIError
from .settings import Settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .schemas import JobCreate, StageSpec

INTEGRATOR_TYPES = (
    "langevin_middle",
    "langevin",
    "brownian",
    "verlet",
    "variable_verlet",
    "variable_langevin",
    "nose_hoover",
)
VARIABLE_STEP_INTEGRATORS = ("variable_verlet", "variable_langevin")
THERMOSTATTED_INTEGRATORS = (
    "langevin_middle",
    "langevin",
    "brownian",
    "variable_langevin",
    "nose_hoover",
)
FRICTION_INTEGRATORS = (
    "langevin_middle",
    "langevin",
    "brownian",
    "variable_langevin",
)
BAROSTAT_TYPES = ("none", "monte_carlo")
INPUT_MODES = ("complex", "protein_ligands", "pdb_id")

FIXED_FORCEFIELDS = ("amber14/protein.ff14SB.xml", "amber14/tip3p.xml")
LIGAND_FORCEFIELD = "openff-2.3.0"

MAX_NAME_LENGTH = 200
MAX_STEPS_PER_STAGE = 50_000_000
MAX_TOTAL_STEPS = 200_000_000
MAX_EQUILIBRATION_STAGES = 10
MAX_LIGANDS = 20
MAX_STAGE_RETRIES = 3


def _limit_error(code: str, message: str, **details: Any) -> APIError:
    return APIError(422, code, message, details or None)


def resolve_steps(stage: "StageSpec") -> int:
    """Resolve a stage duration to an integer number of steps."""

    if stage.steps is not None:
        return stage.steps

    integrator = stage.integrator
    if integrator.type in VARIABLE_STEP_INTEGRATORS:
        raise _limit_error(
            "invalid_stage_duration",
            "Variable-step integrators require an explicit steps value",
        )

    timestep = integrator.timestep_ps
    if timestep is None or timestep <= 0:
        raise _limit_error(
            "invalid_integrator",
            "A fixed-step integrator requires a positive timestep_ps",
        )

    if stage.duration_ns is not None:
        duration_ps = stage.duration_ns * 1000.0
    else:
        duration_ps = stage.duration_ps or 0.0

    steps = round(duration_ps / timestep)
    if steps < 1:
        raise _limit_error(
            "invalid_stage_duration",
            "Stage duration is shorter than one integrator step",
        )
    return steps


def _stage_dict(
    stage: "StageSpec",
    *,
    name: str,
    kind: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "label": stage.label,
        "steps": resolve_steps(stage),
        "report_interval": stage.report_interval,
        "trajectory_interval": stage.trajectory_interval,
        "checkpoint_interval": stage.checkpoint_interval,
        "retries": stage.retries,
        "retry_delay_s": stage.retry_delay_s,
        "initial_velocity_temperature_k": stage.initial_velocity_temperature_k,
        "velocity_seed": stage.velocity_seed,
        "integrator": stage.integrator.model_dump(mode="json", exclude_none=True),
        "barostat": stage.barostat.model_dump(mode="json", exclude_none=True),
    }


def build_canonical_spec(
    request: "JobCreate",
    inputs: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    """Build the canonical, fully resolved job specification."""

    if len(request.equilibration) > settings.max_equilibration_stages:
        raise _limit_error(
            "too_many_equilibration_stages",
            "Too many equilibration stages",
            limit=settings.max_equilibration_stages,
        )

    if len(inputs.get("ligands", [])) > settings.max_ligands:
        raise _limit_error(
            "too_many_ligands",
            "Too many ligand files",
            limit=settings.max_ligands,
        )

    if not request.equilibration and not request.production.enabled:
        raise _limit_error(
            "no_simulation_stage",
            "At least one equilibration or production stage is required",
        )

    equilibration = [
        _stage_dict(stage, name=f"equil-{index:02d}", kind="equilibration")
        for index, stage in enumerate(request.equilibration, 1)
    ]
    production = (
        _stage_dict(
            request.production,
            name="production",
            kind="production",
        )
        if request.production.enabled
        else None
    )

    stages = [*equilibration]
    if production is not None:
        stages.append(production)

    for stage in stages:
        if stage["steps"] > settings.max_steps_per_stage:
            raise _limit_error(
                "stage_too_long",
                f"Stage {stage['name']} exceeds the step limit",
                stage=stage["name"],
                steps=stage["steps"],
                limit=settings.max_steps_per_stage,
            )

    total_steps = sum(stage["steps"] for stage in stages)
    if total_steps > settings.max_total_steps:
        raise _limit_error(
            "job_too_long",
            "Job exceeds the total step limit",
            steps=total_steps,
            limit=settings.max_total_steps,
        )

    return {
        "version": 1,
        "name": request.name,
        "input": inputs,
        "parameterization": request.parameterization.model_dump(mode="json"),
        "minimization": request.minimization.model_dump(mode="json"),
        "equilibration": equilibration,
        "production": production,
        "total_steps": total_steps,
    }


def stage_rows(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the job_stages rows implied by a canonical spec."""

    rows: list[dict[str, Any]] = []
    position = 0
    minimization = canonical["minimization"]
    if minimization.get("enabled"):
        rows.append(
            {
                "name": "minimization",
                "position": position,
                "kind": "minimization",
                "steps_target": 0,
            }
        )
        position += 1
    for stage in canonical.get("equilibration", []):
        rows.append(
            {
                "name": stage["name"],
                "position": position,
                "kind": "equilibration",
                "steps_target": stage["steps"],
            }
        )
        position += 1
    production = canonical.get("production")
    if production is not None:
        rows.append(
            {
                "name": production["name"],
                "position": position,
                "kind": "production",
                "steps_target": production["steps"],
            }
        )
    return rows


def stage_names(canonical: dict[str, Any]) -> list[str]:
    return [row["name"] for row in stage_rows(canonical)]
