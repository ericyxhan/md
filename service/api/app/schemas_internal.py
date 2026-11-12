"""Request and response models for the internal worker protocol.

All internal models forbid unknown fields.  The worker token is the only
credential, and every state-changing call carries the run token returned by
``claim`` so a stale worker cannot mutate a job that has been retried or
reclaimed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Phase = Literal["parameterizing", "minimizing", "simulating", "finalizing"]
StageStatus = Literal[
    "pending", "running", "completed", "failed", "canceled", "skipped"
]
ArtifactKind = Literal[
    "config",
    "log",
    "state",
    "checkpoint",
    "trajectory",
    "structure",
    "view",
    "analysis",
    "metadata",
]
PrepStatus = Literal["queued", "claimed", "running", "completed", "failed", "canceled"]

_WORKER_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class InternalModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class WorkerHeartbeatRequest(InternalModel):
    worker_id: str = Field(
        min_length=1, max_length=64, pattern=_WORKER_ID_PATTERN
    )
    hostname: str = Field(min_length=1, max_length=255)
    gpu_name: str | None = Field(default=None, max_length=255)
    gpu_uuid: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    status: Literal["online", "offline"] = "online"
    current_job_id: str | None = Field(
        default=None, min_length=1, max_length=36
    )
    run_token: str | None = Field(default=None, min_length=1, max_length=36)


class WorkerHeartbeatResponse(InternalModel):
    cancel_requested: bool
    lease_expires_at: str | None = None


class ClaimRequest(InternalModel):
    worker_id: str = Field(
        min_length=1, max_length=64, pattern=_WORKER_ID_PATTERN
    )
    gpu_uuid: str | None = Field(default=None, max_length=128)


class ClaimStage(InternalModel):
    name: str
    kind: str
    status: str
    steps_completed: int
    steps_target: int


class ClaimResponse(InternalModel):
    job_id: str
    run_token: str
    config_path: str
    job_root: str
    restart_mode: str
    restart_stage: str | None
    stages: list[ClaimStage]


class ProgressRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)
    phase: Phase | None = None
    stage: str | None = Field(default=None, max_length=64)
    step: int | None = Field(default=None, ge=0)
    total_steps: int | None = Field(default=None, ge=0)
    percent: float | None = Field(default=None, ge=0.0, le=100.0)
    updated_at: str | None = Field(default=None, max_length=32)


class ProgressResponse(InternalModel):
    cancel_requested: bool
    lease_expires_at: str | None = None


class StageUpdateRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=64)
    status: StageStatus
    steps_completed: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=8000)
    manifest: dict[str, Any] | None = None
    manifest_json: str | dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_manifest(self) -> "StageUpdateRequest":
        if self.manifest is not None and self.manifest_json is not None:
            raise ValueError(
                "provide only one of manifest or manifest_json"
            )
        return self


class StageUpdateResponse(InternalModel):
    ok: bool = True
    cancel_requested: bool = False


class ArtifactInput(InternalModel):
    stage_name: str | None = Field(default=None, max_length=64)
    kind: ArtifactKind
    relative_path: str = Field(min_length=1, max_length=1024)
    size_bytes: int | None = Field(default=None, ge=0)
    content_type: str | None = Field(default=None, max_length=128)


class FinishRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)
    status: Literal["completed", "failed", "canceled"]
    exit_code: int | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=8000)
    artifacts: list[ArtifactInput] = Field(default_factory=list, max_length=2000)


class FinishResponse(InternalModel):
    status: str


# ---------------------------------------------------------------------------
# Internal prep protocol
# ---------------------------------------------------------------------------


class PrepClaimRequest(InternalModel):
    worker_id: str = Field(
        min_length=1, max_length=64, pattern=_WORKER_ID_PATTERN
    )


class PrepClaimResponse(InternalModel):
    prep_job_id: str
    run_token: str
    # Membrane-embed fields
    protein_file_id: str | None = None
    lipid: str | None = None
    box_padding_nm: float | None = None
    orientation: str | None = None
    ionic_strength_molar: float | None = None
    # System-prep fields
    job_type: str | None = None
    steps: list[dict[str, Any]] | None = None
    # Common
    source_path: str | None = None
    work_dir: str | None = None


class PrepProgressRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)
    phase: str | None = Field(default=None, max_length=64)
    percent: float | None = Field(default=None, ge=0.0, le=100.0)
    message: str | None = Field(default=None, max_length=1000)


class PrepProgressResponse(InternalModel):
    cancel_requested: bool
    lease_expires_at: str | None = None


class PrepFinishRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)
    status: Literal["completed", "failed", "canceled"]
    output_file_ids: list[str] = Field(default_factory=list, max_length=100)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=8000)


class PrepFinishResponse(InternalModel):
    status: str


class PrepCancelRequest(InternalModel):
    run_token: str = Field(min_length=1, max_length=36)


class PrepCancelResponse(InternalModel):
    ok: bool = True
