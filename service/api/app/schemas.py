"""Pydantic request and response models.

Every request model forbids unknown fields.  The public API never accepts a
path, command, executable, platform property, or raw TOML document.
"""

from __future__ import annotations

import re
from typing import Any, Literal

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


class SessionLogin(StrictModel):
    password: str = Field(min_length=1, max_length=512)


class SessionOut(BaseModel):
    authenticated: bool
    owner: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None
    auth_method: str | None = None


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


class FileInspectOut(BaseModel):
    """Structure summary for any upload, used to populate chain/ligand pickers."""

    chains: dict[str, dict[str, Any]]
    ligands: list[str]
    components: dict[str, int]
    atom_count: int
    model_count: int
    bounding_box: dict[str, Any] | None = None


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


class EventWithJobOut(EventOut):
    """An event enriched with its parent job for cross-job event feeds."""

    job_id: str
    job_name: str
    job_status: str
    source: str = "job"
    prep_type: str | None = None


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


class ViewFileOut(BaseModel):
    id: str
    name: str
    relative_path: str
    size_bytes: int
    url: str


class ViewOut(BaseModel):
    group: str
    structure: ViewFileOut | None = None
    trajectory: ViewFileOut | None = None
    manifest: ViewFileOut | None = None
    manifest_data: dict | None = None


class ViewListOut(BaseModel):
    items: list[ViewOut]


class SeriesPoint(BaseModel):
    """One downsampled time-series point from a stage's simulation.log."""

    step: int
    time_ps: float | None = None
    potential_energy_kj_mol: float | None = None
    kinetic_energy_kj_mol: float | None = None
    temperature_k: float | None = None
    density_g_ml: float | None = None
    volume_nm3: float | None = None
    speed_ns_day: float | None = None
    elapsed_s: float | None = None


class SeriesOut(BaseModel):
    """Downsampled time series for a completed stage."""

    group: str
    source: str
    source_points: int
    view_points: int
    columns: list[str]
    points: list[SeriesPoint]


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


# ---------------------------------------------------------------------------
# System preparation: membrane embedding
# ---------------------------------------------------------------------------


LipidType = Literal["POPC", "POPE", "DPPC", "DLPC", "DSPC", "SOPC"]


class MembraneEmbedRequest(StrictModel):
    """Request to embed a protein structure into a lipid bilayer."""

    protein_file_id: str = Field(
        min_length=1, max_length=64,
        description="Uploaded protein complex (PDB or mmCIF) file ID",
    )
    lipid: LipidType = Field(default="POPC")
    box_padding_nm: float = Field(
        default=1.5, ge=0.5, le=5.0,
        description="Padding around the protein in the membrane box (nm)",
    )
    orientation: str | None = Field(
        default=None,
        description="Optional membrane orientation: 'pm' or 'pp'",
    )
    ionic_strength_molar: float = Field(
        default=0.15, ge=0.0, le=1.0,
    )


class MembraneEmbedOut(BaseModel):
    prep_job_id: str
    status: str
    embedded_pdb_file_id: str | None = None
    topology_file_id: str | None = None
    error: str | None = None


class PrepJobStatus(BaseModel):
    id: str
    type: str
    status: str
    created_at: str
    completed_at: str | None = None
    output_file_ids: list[str] = []
    error: str | None = None
    phase: str | None = None
    progress_percent: float | None = None
    progress_message: str | None = None
    progress_updated_at: str | None = None
    cancel_requested: bool | None = None
    label: str = ""


# ---------------------------------------------------------------------------
# System preparation: structure operations (ligand removal, chain selection, etc.)
# ---------------------------------------------------------------------------


SystemPrepOperation = Literal[
    "remove_ligand", "select_chain", "add_ligand", "remove_residues", "keep_selection"
]


class SystemPrepStep(StrictModel):
    """One step in a system preparation pipeline."""

    operation: SystemPrepOperation
    ligand_to_remove: str | None = Field(
        default=None,
        min_length=1,
        max_length=5,
        description="Residue name of ligand to remove (for remove_ligand)",
    )
    chain_to_keep: str | None = Field(
        default=None,
        min_length=1,
        max_length=2,
        description="Chain ID to keep (for select_chain)",
    )
    ligand_file_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Ligand file IDs to add (for add_ligand)",
    )
    residue_specs: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=100,
        description="Explicit residue specs {chain, resnum, icode} (for remove_residues/keep_selection)",
    )

    @model_validator(mode="after")
    def _validate_step(self) -> "SystemPrepStep":
        if self.operation == "remove_ligand" and not self.ligand_to_remove:
            raise ValueError("remove_ligand requires ligand_to_remove")
        if self.operation == "select_chain" and not self.chain_to_keep:
            raise ValueError("select_chain requires chain_to_keep")
        if self.operation == "add_ligand" and not self.ligand_file_ids:
            raise ValueError("add_ligand requires at least one ligand_file_id")
        if self.operation in ("remove_residues", "keep_selection") and not self.residue_specs:
            raise ValueError(f"{self.operation} requires residue_specs")
        return self


class SystemPrepRequest(StrictModel):
    """Request to prepare a system by applying one or more structure operations."""

    name: str = Field(min_length=1, max_length=200)
    input_file_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Uploaded PDB file ID (mutually exclusive with pdb_id)",
    )
    pdb_id: str | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="RCSB PDB ID to download (mutually exclusive with input_file_id)",
    )
    steps: list[SystemPrepStep] = Field(
        default_factory=list,
        max_length=10,
        description="Preparation steps to apply in order",
    )

    @model_validator(mode="after")
    def _validate_input(self) -> "SystemPrepRequest":
        if not self.input_file_id and not self.pdb_id:
            raise ValueError("Either input_file_id or pdb_id is required")
        if self.input_file_id and self.pdb_id:
            raise ValueError("input_file_id and pdb_id are mutually exclusive")
        if not self.steps:
            raise ValueError("At least one step is required")
        return self


class SystemPrepOut(BaseModel):
    prep_job_id: str
    status: str
    output_file_ids: list[str] = []
    error: str | None = None


# ---------------------------------------------------------------------------
# Workflows (base systems + derived simulation jobs)
# ---------------------------------------------------------------------------


class WorkflowCreate(StrictModel):
    """Create a workflow from a completed prep/embed output file."""

    name: str = Field(min_length=1, max_length=200)
    source_file_id: str = Field(
        min_length=1, max_length=64,
        description="Output file ID from a completed system-prep or membrane-embed job",
    )
    source_type: str = Field(
        default="system_prep",
        description="Kind of prep job that produced the source file",
    )


class WorkflowJobSummary(BaseModel):
    """Lightweight job representation for workflow listings."""

    id: str
    name: str
    status: str
    phase: str | None
    progress: ProgressOut
    created_at: str
    updated_at: str


class WorkflowOut(BaseModel):
    id: str
    name: str
    source_file_id: str
    source_type: str
    job_count: int
    created_at: str
    updated_at: str


class WorkflowDetailOut(BaseModel):
    id: str
    name: str
    source_file_id: str
    source_type: str
    created_at: str
    updated_at: str
    jobs: list[WorkflowJobSummary]


class WorkflowVariantsRequest(StrictModel):
    """Create N variant simulation jobs from a workflow's base system."""

    count: int = Field(default=1, ge=1, le=50)
    name_template: str = Field(
        default="{name} · variant {n}",
        min_length=1,
        max_length=200,
        description="Template with {name} and {n} placeholders",
    )
    parameterization: ParameterizationSpec | None = Field(
        default=None,
        description="Override parameterization for all variants",
    )
    minimization: MinimizationSpec | None = Field(
        default=None, description="Override minimization for all variants"
    )
    equilibration: list[StageSpec] | None = Field(
        default=None,
        max_length=MAX_EQUILIBRATION_STAGES,
        description="Override equilibration stages for all variants",
    )
    production: ProductionSpec | None = Field(
        default=None, description="Override production spec for all variants"
    )

