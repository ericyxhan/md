"""Pydantic request and response models.

Every request model forbids unknown fields.  The public API never accepts a
path, command, executable, platform property, or raw TOML document.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .policies import (
    BAROSTAT_TYPES,
    INPUT_MODES,
    INTEGRATOR_TYPES,
    MAX_EQUILIBRATION_STAGES,
    MAX_NAME_LENGTH,
    MAX_STAGE_RETRIES,
    VARIABLE_STEP_INTEGRATORS,
)

IntegratorType = Literal[
    "langevin_middle",
    "langevin",
    "brownian",
    "verlet",
    "variable_verlet",
    "variable_langevin",
    "nose_hoover",
]
BarostatType = Literal["none", "monte_carlo"]

_PDB_ID_RE = re.compile(r"^[0-9A-Za-z]{4}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


# ---------------------------------------------------------------------------
# Simulation settings
# ---------------------------------------------------------------------------


class IntegratorSpec(StrictModel):
    type: IntegratorType = "langevin_middle"
    timestep_ps: float | None = Field(default=0.002, ge=0.0001, le=0.01)
    temperature_k: float | None = Field(default=300.0, ge=1.0, le=1000.0)
    friction_per_ps: float | None = Field(default=1.0, ge=0.01, le=100.0)
    collision_frequency_per_ps: float | None = Field(
        default=1.0, ge=0.01, le=100.0
    )
    error_tolerance: float | None = Field(default=0.001, ge=1e-6, le=0.1)
    maximum_step_ps: float | None = Field(default=None, gt=0.0, le=0.01)
    constraint_tolerance: float | None = Field(default=None, gt=0.0, le=1.0)
    integration_force_groups: int | None = Field(default=None, ge=0, le=31)
    random_seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_type_fields(self) -> "IntegratorSpec":
        if self.type in VARIABLE_STEP_INTEGRATORS:
            if self.error_tolerance is None or self.error_tolerance <= 0:
                raise ValueError(
                    "variable-step integrators require error_tolerance"
                )
        elif self.timestep_ps is None or self.timestep_ps <= 0:
            raise ValueError("fixed-step integrators require timestep_ps")

        if self.type in (
            "langevin_middle",
            "langevin",
            "brownian",
            "variable_langevin",
            "nose_hoover",
        ) and (self.temperature_k is None or self.temperature_k <= 0):
            raise ValueError(f"{self.type} requires temperature_k")

        if self.type in (
            "langevin_middle",
            "langevin",
            "brownian",
            "variable_langevin",
        ) and (self.friction_per_ps is None or self.friction_per_ps <= 0):
            raise ValueError(f"{self.type} requires friction_per_ps")

        if self.type == "nose_hoover" and (
            self.collision_frequency_per_ps is None
            or self.collision_frequency_per_ps <= 0
        ):
            raise ValueError("nose_hoover requires collision_frequency_per_ps")
        return self


class BarostatSpec(StrictModel):
    type: BarostatType = "none"
    pressure_bar: float = Field(default=1.0, ge=0.1, le=100.0)
    temperature_k: float | None = Field(default=None, ge=1.0, le=1000.0)
    frequency: int = Field(default=25, ge=1, le=1000)
    random_seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_barostat(self) -> "BarostatSpec":
        if self.type == "monte_carlo":
            if self.pressure_bar <= 0:
                raise ValueError("monte_carlo requires pressure_bar > 0")
            if self.frequency <= 0:
                raise ValueError("monte_carlo requires frequency > 0")
        return self


class StageFields(StrictModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    steps: int | None = Field(default=None, ge=1, le=50_000_000)
    duration_ps: float | None = Field(default=None, gt=0.0, le=1_000_000.0)
    duration_ns: float | None = Field(default=None, gt=0.0, le=10_000.0)
    report_interval: int = Field(default=1000, ge=1, le=1_000_000)
    trajectory_interval: int | None = Field(default=None, ge=0, le=1_000_000)
    checkpoint_interval: int = Field(default=1000, ge=1, le=1_000_000)
    retries: int = Field(default=0, ge=0, le=MAX_STAGE_RETRIES)
    retry_delay_s: float = Field(default=5.0, ge=0.0, le=60.0)
    initial_velocity_temperature_k: float | None = Field(
        default=None, gt=0.0, le=1000.0
    )
    velocity_seed: int | None = Field(default=None, ge=0)
    integrator: IntegratorSpec = Field(default_factory=IntegratorSpec)
    barostat: BarostatSpec = Field(default_factory=BarostatSpec)


def _validate_stage_duration(model: StageFields) -> None:
    duration_fields = [
        model.steps is not None,
        model.duration_ps is not None,
        model.duration_ns is not None,
    ]
    if sum(duration_fields) != 1:
        raise ValueError(
            "set exactly one of steps, duration_ps, or duration_ns"
        )
    if (
        model.integrator.type in VARIABLE_STEP_INTEGRATORS
        and model.steps is None
    ):
        raise ValueError(
            "duration_ps/duration_ns require a fixed-step integrator; "
            "use steps for variable-step integrators"
        )


class StageSpec(StageFields):
    @model_validator(mode="after")
    def _validate_stage(self) -> "StageSpec":
        _validate_stage_duration(self)
        return self


class ProductionSpec(StageFields):
    enabled: bool = False

    @model_validator(mode="after")
    def _validate_production(self) -> "ProductionSpec":
        if self.enabled:
            _validate_stage_duration(self)
        return self


class MinimizationSpec(StrictModel):
    enabled: bool = True
    max_iterations: int = Field(default=0, ge=0, le=100_000)
    tolerance_kj_mol_nm: float = Field(default=10.0, ge=0.1, le=1000.0)


class ParameterizationSpec(StrictModel):
    ph: float = Field(default=7.4, ge=0.0, le=14.0)
    padding_nm: float = Field(default=1.0, ge=0.5, le=2.0)
    ionic_strength_molar: float = Field(default=0.15, ge=0.0, le=1.0)
    add_missing_residues: bool = False
    allow_undefined_stereo: bool = False
    max_ligand_residues: int = Field(default=50, ge=0, le=100)


# ---------------------------------------------------------------------------
# Inputs and job creation
# ---------------------------------------------------------------------------


class InputSpec(StrictModel):
    mode: Literal["complex", "protein_ligands", "pdb_id"]
    complex_file_id: str | None = Field(default=None, min_length=1, max_length=64)
    protein_file_id: str | None = Field(default=None, min_length=1, max_length=64)
    ligand_file_ids: list[str] = Field(default_factory=list, max_length=20)
    pdb_id: str | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def _validate_mode(self) -> "InputSpec":
        if self.mode == "complex":
            if not self.complex_file_id:
                raise ValueError("complex mode requires complex_file_id")
            if self.protein_file_id or self.ligand_file_ids or self.pdb_id:
                raise ValueError(
                    "complex mode accepts only complex_file_id"
                )
        elif self.mode == "protein_ligands":
            if not self.protein_file_id:
                raise ValueError(
                    "protein_ligands mode requires protein_file_id"
                )
            if not self.ligand_file_ids:
                raise ValueError(
                    "protein_ligands mode requires at least one ligand_file_id"
                )
            if self.complex_file_id or self.pdb_id:
                raise ValueError(
                    "protein_ligands mode accepts only protein and ligand files"
                )
            if len(set(self.ligand_file_ids)) != len(self.ligand_file_ids):
                raise ValueError("ligand_file_ids must be unique")
        else:
            if not self.pdb_id or not _PDB_ID_RE.match(self.pdb_id):
                raise ValueError(
                    "pdb_id mode requires a four-character PDB ID"
                )
            if (
                self.complex_file_id
                or self.protein_file_id
                or self.ligand_file_ids
            ):
                raise ValueError("pdb_id mode accepts only pdb_id")
        return self


class JobCreate(StrictModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    input: InputSpec
    parameterization: ParameterizationSpec = Field(
        default_factory=ParameterizationSpec
    )
    minimization: MinimizationSpec = Field(default_factory=MinimizationSpec)
    equilibration: list[StageSpec] = Field(
        default_factory=list, max_length=MAX_EQUILIBRATION_STAGES
    )
    production: ProductionSpec = Field(default_factory=ProductionSpec)

    @model_validator(mode="after")
    def _at_least_one_stage(self) -> "JobCreate":
        if not self.equilibration and not self.production.enabled:
            raise ValueError(
                "at least one equilibration or production stage is required"
            )
        return self


class JobValidateRequest(JobCreate):
    """The dry-validation request is the same as the create request."""


class RetryRequest(StrictModel):
    mode: Literal["resume", "restart", "restart_stage", "reparameterize"]
    stage: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_mode(self) -> "RetryRequest":
        if self.mode == "restart_stage":
            if not self.stage:
                raise ValueError("restart_stage requires a stage name")
        elif self.stage is not None:
            raise ValueError("stage is only valid for restart_stage")
        return self



# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class FileOut(BaseModel):
    id: str
    name: str
    size_bytes: int
    sha256: str
    content_type: str
    created_at: str


class StageOut(BaseModel):
    name: str
    kind: str
    status: str
    steps_completed: int
    steps_target: int
    attempts: int
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ProgressOut(BaseModel):
    step: int | None = None
    total_steps: int | None = None
    percent: float | None = None
    updated_at: str | None = None


class JobErrorOut(BaseModel):
    code: str
    message: str


class JobOut(BaseModel):
    id: str
    name: str
    status: str
    phase: str | None
    input_mode: str
    attempt: int
    current_stage: str | None
    progress: ProgressOut
    queue_position: int | None
    stages: list[StageOut]
    error: JobErrorOut | None
    created_at: str
    updated_at: str
    queued_at: str | None
    started_at: str | None
    completed_at: str | None


class JobListOut(BaseModel):
    items: list[JobOut]
    next_cursor: str | None = None


class EventOut(BaseModel):
    id: int
    type: str
    message: str
    data: dict | None = None
    created_at: str


class ArtifactOut(BaseModel):
    id: str
    stage_name: str | None = None
    kind: str
    relative_path: str
    name: str
    size_bytes: int
    content_type: str
    created_at: str


class ArtifactListOut(BaseModel):
    items: list[ArtifactOut]


class LogOut(BaseModel):
    name: str
    relative_path: str
    size_bytes: int
    content_type: str
    updated_at: str


class LogListOut(BaseModel):
    items: list[LogOut]


class LogTailOut(BaseModel):
    name: str
    relative_path: str
    content: str
    lines: int
    truncated: bool
    size_bytes: int


class JobPlanOut(BaseModel):
    valid: bool
    config_toml: str
    plan: dict


INTEGRATOR_CHOICES = INTEGRATOR_TYPES
BAROSTAT_CHOICES = BAROSTAT_TYPES
INPUT_MODE_CHOICES = INPUT_MODES
