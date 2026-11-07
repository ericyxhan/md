#!/usr/bin/env python3
"""Typed, validated configuration for the OpenMM workflow.

The user-facing configuration is a TOML file (see ``config.toml``).  This
module turns that file into immutable dataclasses so the rest of the code can
work with explicit values instead of a nested dictionary full of optional
keys.

Design goals
------------
* A misspelled key or an impossible value fails immediately with a message
  that names the exact setting.
* Paths are resolved relative to the configuration file, not the current
  working directory.  This makes the workflow behave the same locally, from a
  different directory, and inside the Docker image.
* Defaults are visible in one place and can be overridden by a short CLI flag
  such as ``--platform CPU``.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# Allowed values
# ---------------------------------------------------------------------------

_INTEGRATOR_TYPES = {
    "langevin_middle",
    "langevin",
    "brownian",
    "verlet",
    "variable_verlet",
    "variable_langevin",
    "nose_hoover",
}

_THERMOSTATTED_INTEGRATORS = {
    "langevin_middle",
    "langevin",
    "brownian",
    "variable_langevin",
    "nose_hoover",
}

_FRICTION_INTEGRATORS = {
    "langevin_middle",
    "langevin",
    "brownian",
    "variable_langevin",
}

_VARIABLE_STEP_INTEGRATORS = {"variable_verlet", "variable_langevin"}

_BAROSTAT_TYPES = {"none", "monte_carlo"}

_STAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_PDB_ID_RE = re.compile(r"^[0-9A-Za-z]{4}$")


class ConfigError(ValueError):
    """Raised when a configuration file is missing, malformed, or invalid."""


# ---------------------------------------------------------------------------
# Small parsing helpers
# ---------------------------------------------------------------------------


def _check_keys(table: Mapping[str, Any], allowed: set[str], context: str) -> None:
    """Reject unknown keys so typos do not silently fall back to defaults."""
    if not isinstance(table, Mapping):
        raise ConfigError(f"{context} must be a table")
    unknown = sorted(set(table) - allowed)
    if unknown:
        names = ", ".join(unknown)
        raise ConfigError(f"{context}: unknown key(s): {names}")


def _string(
    table: Mapping[str, Any],
    key: str,
    default: str,
    context: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"{context}.{key} must be a string")
    if not allow_empty and not value.strip():
        raise ConfigError(f"{context}.{key} must not be empty")
    return value.strip()


def _string_list(
    table: Mapping[str, Any],
    key: str,
    default: tuple[str, ...],
    context: str,
) -> tuple[str, ...]:
    value = table.get(key, list(default))
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ConfigError(f"{context}.{key} must be an array of non-empty strings")
    return tuple(item.strip() for item in value)


def _number(
    table: Mapping[str, Any],
    key: str,
    default: float,
    context: str,
    *,
    minimum: float | None = None,
) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{context}.{key} must be a number")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{context}.{key} must be >= {minimum:g}")
    return float(value)


def _optional_number(
    table: Mapping[str, Any],
    key: str,
    context: str,
    *,
    minimum: float | None = None,
) -> float | None:
    if key not in table:
        return None
    return _number(table, key, 0.0, context, minimum=minimum)


def _integer(
    table: Mapping[str, Any],
    key: str,
    default: int,
    context: str,
    *,
    minimum: int | None = None,
) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{context}.{key} must be an integer")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{context}.{key} must be >= {minimum}")
    return value


def _optional_integer(
    table: Mapping[str, Any],
    key: str,
    context: str,
    *,
    minimum: int | None = None,
) -> int | None:
    if key not in table:
        return None
    return _integer(table, key, 0, context, minimum=minimum)


def _boolean(table: Mapping[str, Any], key: str, default: bool, context: str) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{context}.{key} must be true or false")
    return value


def _resolve_path(value: str, base_dir: Path) -> Path:
    """Expand ``~``/environment variables and resolve relative to *base_dir*."""
    expanded = os.path.expandvars(os.path.expanduser(value))
    path = Path(expanded)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _optional_path(
    table: Mapping[str, Any],
    key: str,
    base_dir: Path,
    context: str,
) -> Path | None:
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise ConfigError(f"{context}.{key} must be a string")
    value = value.strip()
    if not value:
        return None
    return _resolve_path(value, base_dir)


# ---------------------------------------------------------------------------
# Integrator and barostat settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IntegratorConfig:
    """OpenMM integrator settings, with units in the name.

    Fixed-step integrators use ``timestep_ps``.  Variable-step integrators use
    ``error_tolerance`` instead and are therefore only compatible with a stage
    that specifies ``steps`` (not a duration).
    """

    type: str = "langevin_middle"
    timestep_ps: float | None = 0.002
    temperature_k: float | None = 300.0
    friction_per_ps: float | None = 1.0
    collision_frequency_per_ps: float | None = 1.0
    error_tolerance: float | None = 0.001
    maximum_step_ps: float | None = None
    constraint_tolerance: float | None = None
    integration_force_groups: int | None = None
    random_seed: int | None = None

    @property
    def fixed_step(self) -> bool:
        return self.type not in _VARIABLE_STEP_INTEGRATORS

    def validate(self, context: str) -> None:
        if self.type not in _INTEGRATOR_TYPES:
            allowed = ", ".join(sorted(_INTEGRATOR_TYPES))
            raise ConfigError(f"{context}.type must be one of: {allowed}")

        if self.fixed_step:
            if self.timestep_ps is None or self.timestep_ps <= 0:
                raise ConfigError(f"{context}.timestep_ps must be > 0")
        else:
            if self.error_tolerance is None or self.error_tolerance <= 0:
                raise ConfigError(f"{context}.error_tolerance must be > 0")
            if (
                self.maximum_step_ps is not None
                and self.maximum_step_ps <= 0
            ):
                raise ConfigError(f"{context}.maximum_step_ps must be > 0")

        if self.type in _THERMOSTATTED_INTEGRATORS:
            if self.temperature_k is None or self.temperature_k <= 0:
                raise ConfigError(f"{context}.temperature_k must be > 0")

        if self.type in _FRICTION_INTEGRATORS:
            if self.friction_per_ps is None or self.friction_per_ps <= 0:
                raise ConfigError(f"{context}.friction_per_ps must be > 0")

        if self.type == "nose_hoover":
            if (
                self.collision_frequency_per_ps is None
                or self.collision_frequency_per_ps <= 0
            ):
                raise ConfigError(
                    f"{context}.collision_frequency_per_ps must be > 0"
                )

        if self.constraint_tolerance is not None and self.constraint_tolerance <= 0:
            raise ConfigError(f"{context}.constraint_tolerance must be > 0")
        if (
            self.integration_force_groups is not None
            and self.integration_force_groups < 0
        ):
            raise ConfigError(f"{context}.integration_force_groups must be >= 0")
        if self.random_seed is not None and self.random_seed < 0:
            raise ConfigError(f"{context}.random_seed must be >= 0")


@dataclass(frozen=True)
class BarostatConfig:
    """Pressure control settings.  ``none`` means constant volume."""

    type: str = "none"
    pressure_bar: float = 1.0
    temperature_k: float | None = None
    frequency: int = 25
    random_seed: int | None = None

    def validate(self, context: str) -> None:
        if self.type not in _BAROSTAT_TYPES:
            allowed = ", ".join(sorted(_BAROSTAT_TYPES))
            raise ConfigError(f"{context}.type must be one of: {allowed}")
        if self.type == "none":
            return
        if self.pressure_bar <= 0:
            raise ConfigError(f"{context}.pressure_bar must be > 0")
        if self.temperature_k is None or self.temperature_k <= 0:
            raise ConfigError(f"{context}.temperature_k must be > 0")
        if self.frequency <= 0:
            raise ConfigError(f"{context}.frequency must be > 0")
        if self.random_seed is not None and self.random_seed < 0:
            raise ConfigError(f"{context}.random_seed must be >= 0")


# ---------------------------------------------------------------------------
# Simulation stage settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageConfig:
    """One dynamics stage (an equilibration stage or the production stage)."""

    name: str
    steps: int
    report_interval: int = 1000
    trajectory_interval: int | None = None
    checkpoint_interval: int = 1000
    retries: int = 0
    retry_delay_s: float = 5.0
    initial_velocity_temperature_k: float | None = None
    velocity_seed: int | None = None
    integrator: IntegratorConfig = field(default_factory=IntegratorConfig)
    barostat: BarostatConfig = field(default_factory=BarostatConfig)

    @property
    def trajectory_report_interval(self) -> int | None:
        """DCD interval, or ``None`` when trajectories are disabled.

        Leaving ``trajectory_interval`` unset uses the state-log interval.
        Setting it to zero explicitly disables the DCD trajectory.
        """
        if self.trajectory_interval is None:
            return self.report_interval
        if self.trajectory_interval == 0:
            return None
        return self.trajectory_interval

    @property
    def velocity_temperature_k(self) -> float:
        """Temperature used when this stage starts from fresh coordinates."""
        if self.initial_velocity_temperature_k is not None:
            return self.initial_velocity_temperature_k
        if self.integrator.temperature_k is not None:
            return self.integrator.temperature_k
        return 300.0

    def validate(self, context: str) -> None:
        if not _STAGE_NAME_RE.match(self.name):
            raise ConfigError(
                f"{context}.name must contain only letters, digits, '.', '_', or '-'"
            )
        if self.name == "minimization":
            raise ConfigError(
                f"{context}.name 'minimization' is reserved for the minimization step"
            )
        if self.steps < 1:
            raise ConfigError(f"{context}: steps must be >= 1")
        if self.report_interval < 1:
            raise ConfigError(f"{context}.report_interval must be >= 1")
        if self.checkpoint_interval < 1:
            raise ConfigError(f"{context}.checkpoint_interval must be >= 1")
        if self.trajectory_interval is not None and self.trajectory_interval < 0:
            raise ConfigError(f"{context}.trajectory_interval must be >= 0")
        if self.retries < 0:
            raise ConfigError(f"{context}.retries must be >= 0")
        if self.retry_delay_s < 0:
            raise ConfigError(f"{context}.retry_delay_s must be >= 0")
        if (
            self.initial_velocity_temperature_k is not None
            and self.initial_velocity_temperature_k <= 0
        ):
            raise ConfigError(
                f"{context}.initial_velocity_temperature_k must be > 0"
            )
        if self.velocity_seed is not None and self.velocity_seed < 0:
            raise ConfigError(f"{context}.velocity_seed must be >= 0")
        self.integrator.validate(f"{context}.integrator")
        self.barostat.validate(f"{context}.barostat")


@dataclass(frozen=True)
class MinimizationConfig:
    """Energy-minimization settings applied before the first dynamics stage."""

    enabled: bool = True
    max_iterations: int = 0
    tolerance_kj_mol_nm: float = 10.0

    def validate(self, context: str = "minimization") -> None:
        if self.max_iterations < 0:
            raise ConfigError(f"{context}.max_iterations must be >= 0")
        if self.tolerance_kj_mol_nm <= 0:
            raise ConfigError(f"{context}.tolerance_kj_mol_nm must be > 0")


# ---------------------------------------------------------------------------
# Run, input, and parameterization settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunConfig:
    """Where and how the simulation runs."""

    output_dir: Path
    platform: str = "CUDA"
    platform_properties: Mapping[str, str] = field(default_factory=dict)

    def validate(self, context: str = "run") -> None:
        if not self.platform.strip():
            raise ConfigError(f"{context}.platform must not be empty")
        for key, value in self.platform_properties.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ConfigError(
                    f"{context}.platform_properties must map strings to strings"
                )


@dataclass(frozen=True)
class InputConfig:
    """Exactly one input mode: complex, protein (+ ligands), or PDB ID."""

    complex_path: Path | None = None
    protein_path: Path | None = None
    ligand_paths: tuple[Path, ...] = ()
    pdb_id: str | None = None

    def validate(self, context: str = "input") -> None:
        sources = [
            self.complex_path is not None,
            self.protein_path is not None,
            self.pdb_id is not None,
        ]
        if sum(sources) != 1:
            raise ConfigError(
                f"{context}: set exactly one of complex, protein, or pdb_id"
            )
        if self.pdb_id is not None and self.ligand_paths:
            raise ConfigError(
                f"{context}: pdb_id already describes a complex; do not add ligands"
            )
        if self.complex_path is not None and self.ligand_paths:
            raise ConfigError(
                f"{context}: complex already contains its ligands; "
                "use protein + ligands instead"
            )


@dataclass(frozen=True)
class ParameterizationConfig:
    """Settings for the CPU-only prepare_system.py environment."""

    python: Path | None
    forcefields: tuple[str, ...]
    ligand_forcefield: str
    ph: float
    padding_nm: float
    ionic_strength_molar: float
    add_missing_residues: bool
    allow_undefined_stereo: bool
    max_ligand_residues: int
    ccd_cache: Path
    reuse_existing: bool

    def validate(self, context: str = "parameterization") -> None:
        if not self.forcefields:
            raise ConfigError(f"{context}.forcefields must not be empty")
        if not self.ligand_forcefield.strip():
            raise ConfigError(f"{context}.ligand_forcefield must not be empty")
        if not 0.0 <= self.ph <= 14.0:
            raise ConfigError(f"{context}.ph must be between 0 and 14")
        if self.padding_nm <= 0:
            raise ConfigError(f"{context}.padding_nm must be > 0")
        if self.ionic_strength_molar < 0:
            raise ConfigError(f"{context}.ionic_strength_molar must be >= 0")
        if self.max_ligand_residues < 0:
            raise ConfigError(f"{context}.max_ligand_residues must be >= 0")


@dataclass(frozen=True)
class WorkflowConfig:
    """Complete, validated workflow configuration."""

    config_path: Path
    run: RunConfig
    input: InputConfig
    parameterization: ParameterizationConfig
    minimization: MinimizationConfig
    equilibration: tuple[StageConfig, ...]
    production: StageConfig | None

    def validate(self) -> None:
        self.run.validate()
        self.input.validate()
        self.parameterization.validate()
        self.minimization.validate()

        names: list[str] = []
        for index, stage in enumerate(self.equilibration, 1):
            stage.validate(f"equilibration[{index}]")
            names.append(stage.name)
        if self.production is not None:
            self.production.validate("production")
            names.append(self.production.name)

        if not names:
            raise ConfigError(
                "Configuration must define at least one equilibration or "
                "production stage"
            )
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ConfigError(
                "Stage names must be unique; duplicated: " + ", ".join(duplicates)
            )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_integrator(table: Mapping[str, Any], context: str) -> IntegratorConfig:
    _check_keys(
        table,
        {
            "type",
            "timestep_ps",
            "temperature_k",
            "friction_per_ps",
            "collision_frequency_per_ps",
            "error_tolerance",
            "maximum_step_ps",
            "constraint_tolerance",
            "integration_force_groups",
            "random_seed",
        },
        context,
    )
    integrator = IntegratorConfig(
        type=_string(table, "type", "langevin_middle", context).lower(),
        timestep_ps=_number(table, "timestep_ps", 0.002, context),
        temperature_k=_number(table, "temperature_k", 300.0, context),
        friction_per_ps=_number(table, "friction_per_ps", 1.0, context),
        collision_frequency_per_ps=_number(
            table, "collision_frequency_per_ps", 1.0, context
        ),
        error_tolerance=_number(table, "error_tolerance", 0.001, context),
        maximum_step_ps=_optional_number(table, "maximum_step_ps", context),
        constraint_tolerance=_optional_number(
            table, "constraint_tolerance", context
        ),
        integration_force_groups=_optional_integer(
            table, "integration_force_groups", context
        ),
        random_seed=_optional_integer(table, "random_seed", context),
    )
    integrator.validate(context)
    return integrator


def _parse_barostat(table: Mapping[str, Any], context: str) -> BarostatConfig:
    _check_keys(
        table,
        {"type", "pressure_bar", "temperature_k", "frequency", "random_seed"},
        context,
    )
    # Validation is deferred until the stage parser has had a chance to
    # inherit the integrator temperature.
    return BarostatConfig(
        type=_string(table, "type", "none", context).lower(),
        pressure_bar=_number(table, "pressure_bar", 1.0, context),
        temperature_k=_optional_number(table, "temperature_k", context),
        frequency=_integer(table, "frequency", 25, context),
        random_seed=_optional_integer(table, "random_seed", context),
    )


def _resolve_steps(
    table: Mapping[str, Any],
    integrator: IntegratorConfig,
    context: str,
) -> int:
    keys = [key for key in ("steps", "duration_ps", "duration_ns") if key in table]
    if len(keys) != 1:
        raise ConfigError(
            f"{context}: set exactly one of steps, duration_ps, or duration_ns"
        )

    if "steps" in table:
        return _integer(table, "steps", 1, context, minimum=1)

    if not integrator.fixed_step:
        raise ConfigError(
            f"{context}: duration_ps/duration_ns require a fixed-step "
            "integrator; use steps for variable-step integrators"
        )

    if "duration_ps" in table:
        duration_ps = _number(table, "duration_ps", 1.0, context)
    else:
        duration_ps = _number(table, "duration_ns", 0.001, context) * 1000.0

    if duration_ps <= 0:
        raise ConfigError(f"{context}: duration must be > 0")
    if integrator.timestep_ps is None or integrator.timestep_ps <= 0:
        raise ConfigError(f"{context}.integrator.timestep_ps must be > 0")

    steps = round(duration_ps / integrator.timestep_ps)
    if steps < 1:
        raise ConfigError(
            f"{context}: duration is shorter than one integrator step"
        )
    return steps


def _parse_stage(
    table: Mapping[str, Any],
    *,
    default_name: str,
    context: str,
) -> StageConfig:
    _check_keys(
        table,
        {
            "name",
            "steps",
            "duration_ps",
            "duration_ns",
            "report_interval",
            "trajectory_interval",
            "checkpoint_interval",
            "retries",
            "retry_delay_s",
            "initial_velocity_temperature_k",
            "velocity_seed",
            "integrator",
            "barostat",
        },
        context,
    )

    integrator = _parse_integrator(table.get("integrator", {}), f"{context}.integrator")
    barostat = _parse_barostat(table.get("barostat", {}), f"{context}.barostat")

    # A barostat at the same temperature as the thermostat is almost always
    # what the user means, so inherit it unless explicitly supplied.
    if barostat.type == "monte_carlo" and barostat.temperature_k is None:
        barostat = replace(barostat, temperature_k=integrator.temperature_k)

    trajectory_interval = _optional_integer(
        table, "trajectory_interval", context
    )
    stage = StageConfig(
        name=_string(table, "name", default_name, context),
        steps=_resolve_steps(table, integrator, context),
        report_interval=_integer(table, "report_interval", 1000, context),
        trajectory_interval=trajectory_interval,
        checkpoint_interval=_integer(table, "checkpoint_interval", 1000, context),
        retries=_integer(table, "retries", 0, context),
        retry_delay_s=_number(table, "retry_delay_s", 5.0, context),
        initial_velocity_temperature_k=_optional_number(
            table, "initial_velocity_temperature_k", context
        ),
        velocity_seed=_optional_integer(table, "velocity_seed", context),
        integrator=integrator,
        barostat=barostat,
    )
    stage.validate(context)
    return stage


def _parse_run(
    table: Mapping[str, Any],
    base_dir: Path,
    *,
    output_dir_override: Path | None,
    platform_override: str | None,
) -> RunConfig:
    _check_keys(table, {"output_dir", "platform", "platform_properties"}, "run")

    output_value = _string(table, "output_dir", "outputs", "run")
    output_dir = (
        output_dir_override
        if output_dir_override is not None
        else _resolve_path(output_value, base_dir)
    )

    properties_table = table.get("platform_properties", {})
    if not isinstance(properties_table, Mapping):
        raise ConfigError("run.platform_properties must be a table")
    platform_properties: dict[str, str] = {}
    for key, value in properties_table.items():
        if not isinstance(value, str):
            raise ConfigError(
                f"run.platform_properties.{key} must be a string"
            )
        platform_properties[key] = value

    platform = (
        platform_override or _string(table, "platform", "CUDA", "run")
    ).strip()
    run = RunConfig(
        output_dir=output_dir,
        platform=platform,
        platform_properties=platform_properties,
    )
    run.validate()
    return run


def _parse_input(table: Mapping[str, Any] | None, base_dir: Path) -> InputConfig:
    if table is None:
        raise ConfigError("Missing required [input] section")
    _check_keys(table, {"complex", "protein", "ligands", "pdb_id"}, "input")

    complex_path = _optional_path(table, "complex", base_dir, "input")
    protein_path = _optional_path(table, "protein", base_dir, "input")
    ligand_values = _string_list(table, "ligands", (), "input")
    ligand_paths = tuple(_resolve_path(value, base_dir) for value in ligand_values)

    pdb_id_value = table.get("pdb_id")
    pdb_id: str | None = None
    if pdb_id_value is not None:
        if not isinstance(pdb_id_value, str):
            raise ConfigError("input.pdb_id must be a string")
        pdb_id = pdb_id_value.strip().upper()
        if not _PDB_ID_RE.match(pdb_id):
            raise ConfigError(
                "input.pdb_id must be a four-character RCSB PDB ID"
            )

    config = InputConfig(
        complex_path=complex_path,
        protein_path=protein_path,
        ligand_paths=ligand_paths,
        pdb_id=pdb_id,
    )
    config.validate()
    return config


def _parse_parameterization(
    table: Mapping[str, Any],
    base_dir: Path,
) -> ParameterizationConfig:
    context = "parameterization"
    _check_keys(
        table,
        {
            "python",
            "forcefields",
            "ligand_forcefield",
            "ph",
            "padding_nm",
            "ionic_strength_molar",
            "add_missing_residues",
            "allow_undefined_stereo",
            "max_ligand_residues",
            "ccd_cache",
            "reuse_existing",
        },
        context,
    )

    ccd_cache_value = _string(
        table,
        "ccd_cache",
        "~/.cache/openmm-parameterizer/ccd",
        context,
    )
    config = ParameterizationConfig(
        python=_optional_path(table, "python", base_dir, context),
        forcefields=_string_list(
            table,
            "forcefields",
            ("amber14/protein.ff14SB.xml", "amber14/tip3p.xml"),
            context,
        ),
        ligand_forcefield=_string(
            table, "ligand_forcefield", "openff-2.3.0", context
        ),
        ph=_number(table, "ph", 7.4, context),
        padding_nm=_number(table, "padding_nm", 1.0, context),
        ionic_strength_molar=_number(
            table, "ionic_strength_molar", 0.15, context
        ),
        add_missing_residues=_boolean(
            table, "add_missing_residues", False, context
        ),
        allow_undefined_stereo=_boolean(
            table, "allow_undefined_stereo", False, context
        ),
        max_ligand_residues=_integer(
            table, "max_ligand_residues", 50, context
        ),
        ccd_cache=_resolve_path(ccd_cache_value, base_dir),
        reuse_existing=_boolean(table, "reuse_existing", True, context),
    )
    config.validate()
    return config


def _parse_minimization(table: Mapping[str, Any]) -> MinimizationConfig:
    context = "minimization"
    _check_keys(
        table,
        {"enabled", "max_iterations", "tolerance_kj_mol_nm"},
        context,
    )
    config = MinimizationConfig(
        enabled=_boolean(table, "enabled", True, context),
        max_iterations=_integer(table, "max_iterations", 0, context),
        tolerance_kj_mol_nm=_number(
            table, "tolerance_kj_mol_nm", 10.0, context
        ),
    )
    config.validate()
    return config


def _parse_equilibration(value: Any) -> tuple[StageConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError(
            "[equilibration] must be an array of tables; use [[equilibration]]"
        )
    stages: list[StageConfig] = []
    for index, table in enumerate(value, 1):
        if not isinstance(table, Mapping):
            raise ConfigError(f"equilibration[{index}] must be a table")
        stages.append(
            _parse_stage(
                table,
                default_name=f"equilibration-{index}",
                context=f"equilibration[{index}]",
            )
        )
    return tuple(stages)


def _parse_production(value: Any) -> StageConfig | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ConfigError("[production] must be a table")
    table = dict(value)
    enabled = table.pop("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError("production.enabled must be true or false")
    if not enabled:
        return None
    return _parse_stage(table, default_name="production", context="production")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def load_config(
    path: str | Path,
    *,
    output_dir_override: Path | None = None,
    platform_override: str | None = None,
) -> WorkflowConfig:
    """Read and validate a TOML configuration file.

    Relative paths inside the file are resolved against the directory that
    contains the file.  CLI overrides for the output directory are resolved by
    the caller and passed in already absolute.
    """
    config_path = Path(path).expanduser()
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid TOML: {exc}") from exc

    _check_keys(
        data,
        {
            "run",
            "input",
            "parameterization",
            "minimization",
            "equilibration",
            "production",
        },
        "configuration",
    )

    base_dir = config_path.parent
    run_table = data.get("run", {})
    if not isinstance(run_table, Mapping):
        raise ConfigError("[run] must be a table")

    config = WorkflowConfig(
        config_path=config_path,
        run=_parse_run(
            run_table,
            base_dir,
            output_dir_override=output_dir_override,
            platform_override=platform_override,
        ),
        input=_parse_input(data.get("input"), base_dir),
        parameterization=_parse_parameterization(
            data.get("parameterization", {}), base_dir
        ),
        minimization=_parse_minimization(data.get("minimization", {})),
        equilibration=_parse_equilibration(data.get("equilibration")),
        production=_parse_production(data.get("production")),
    )
    config.validate()
    return config
