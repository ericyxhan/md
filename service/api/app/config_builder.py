"""Generate a safe TOML configuration from a canonical job specification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomli_w

from .policies import FIXED_FORCEFIELDS, LIGAND_FORCEFIELD, THERMOSTATTED_INTEGRATORS
from .settings import Settings
from .simulation_config import load_workflow_config


def _absolute_inputs(canonical: dict[str, Any], job_root: Path) -> dict[str, Any]:
    inputs = canonical["input"]
    table: dict[str, Any] = {}
    if inputs.get("complex"):
        table["complex"] = str(job_root / inputs["complex"])
    if inputs.get("protein"):
        table["protein"] = str(job_root / inputs["protein"])
    if inputs.get("ligands"):
        table["ligands"] = [
            str(job_root / ligand) for ligand in inputs["ligands"]
        ]
    return table


def _integrator_table(integrator: dict[str, Any]) -> dict[str, Any]:
    kind = integrator["type"]
    table: dict[str, Any] = {"type": kind}

    if kind in ("variable_verlet", "variable_langevin"):
        table["error_tolerance"] = integrator["error_tolerance"]
        if integrator.get("maximum_step_ps") is not None:
            table["maximum_step_ps"] = integrator["maximum_step_ps"]
    else:
        table["timestep_ps"] = integrator["timestep_ps"]

    if kind in THERMOSTATTED_INTEGRATORS and integrator.get("temperature_k") is not None:
        table["temperature_k"] = integrator["temperature_k"]
    if kind in (
        "langevin_middle",
        "langevin",
        "brownian",
        "variable_langevin",
    ) and integrator.get("friction_per_ps") is not None:
        table["friction_per_ps"] = integrator["friction_per_ps"]
    if kind == "nose_hoover" and integrator.get(
        "collision_frequency_per_ps"
    ) is not None:
        table["collision_frequency_per_ps"] = integrator[
            "collision_frequency_per_ps"
        ]

    for key in ("constraint_tolerance", "integration_force_groups", "random_seed"):
        if integrator.get(key) is not None:
            table[key] = integrator[key]
    return table


def _barostat_table(barostat: dict[str, Any]) -> dict[str, Any]:
    if barostat["type"] != "monte_carlo":
        return {"type": "none"}
    table: dict[str, Any] = {
        "type": "monte_carlo",
        "pressure_bar": barostat["pressure_bar"],
        "frequency": barostat["frequency"],
    }
    if barostat.get("temperature_k") is not None:
        table["temperature_k"] = barostat["temperature_k"]
    if barostat.get("random_seed") is not None:
        table["random_seed"] = barostat["random_seed"]
    return table


def _stage_table(stage: dict[str, Any]) -> dict[str, Any]:
    table: dict[str, Any] = {
        "name": stage["name"],
        "steps": stage["steps"],
        "report_interval": stage["report_interval"],
        "checkpoint_interval": stage["checkpoint_interval"],
        "retries": stage["retries"],
        "retry_delay_s": stage["retry_delay_s"],
        "integrator": _integrator_table(stage["integrator"]),
        "barostat": _barostat_table(stage["barostat"]),
    }
    if stage.get("trajectory_interval") is not None:
        table["trajectory_interval"] = stage["trajectory_interval"]
    if stage.get("initial_velocity_temperature_k") is not None:
        table["initial_velocity_temperature_k"] = stage[
            "initial_velocity_temperature_k"
        ]
    if stage.get("velocity_seed") is not None:
        table["velocity_seed"] = stage["velocity_seed"]
    return table


def build_config_document(
    canonical: dict[str, Any],
    job_root: str | Path,
    settings: Settings,
) -> dict[str, Any]:
    """Return the configuration as a TOML-serializable dictionary."""

    root = Path(job_root)
    parameterization = canonical["parameterization"]
    minimization = canonical["minimization"]

    document: dict[str, Any] = {
        "run": {
            "output_dir": str(root / "outputs"),
            "platform": settings.simulation_platform,
        },
        "input": _absolute_inputs(canonical, root),
        "parameterization": {
            "forcefields": list(FIXED_FORCEFIELDS),
            "ligand_forcefield": LIGAND_FORCEFIELD,
            "ph": parameterization["ph"],
            "padding_nm": parameterization["padding_nm"],
            "ionic_strength_molar": parameterization["ionic_strength_molar"],
            "add_missing_residues": parameterization["add_missing_residues"],
            "allow_undefined_stereo": parameterization["allow_undefined_stereo"],
            "max_ligand_residues": parameterization["max_ligand_residues"],
            "ccd_cache": str(
                Path(settings.data_root).expanduser().resolve() / "cache" / "ccd"
            ),
            "reuse_existing": True,
        },
        "minimization": {
            "enabled": minimization["enabled"],
            "max_iterations": minimization["max_iterations"],
            "tolerance_kj_mol_nm": minimization["tolerance_kj_mol_nm"],
        },
    }

    equilibration = [
        _stage_table(stage) for stage in canonical.get("equilibration", [])
    ]
    if equilibration:
        document["equilibration"] = equilibration

    production = canonical.get("production")
    if production is not None:
        document["production"] = _stage_table(production)

    return document


def build_config_toml(
    canonical: dict[str, Any],
    job_root: str | Path,
    settings: Settings,
) -> str:
    return tomli_w.dumps(build_config_document(canonical, job_root, settings))


def write_config(
    canonical: dict[str, Any],
    job_root: str | Path,
    settings: Settings,
) -> Path:
    """Write and validate ``config.toml`` in a job workspace.

    ``config.load_config`` is the final gate.  Pydantic should have rejected
    bad input first, so a validation failure here is a server bug and is
    surfaced as a 500 rather than a user validation error.
    """

    path = Path(job_root) / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_config_toml(canonical, job_root, settings), encoding="utf-8")
    load_workflow_config(path)
    return path
