"""Environment-backed application settings.

The defaults are the v1 deployment defaults recorded in
``docs/service-implementation-plan.md``.  All values can be overridden with
environment variables of the same name (case-insensitive).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIB = 1024 * 1024


class Settings(BaseSettings):
    """Runtime configuration for the API process."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Persistence ------------------------------------------------------
    database_url: str = "sqlite:////db/app.db"
    data_root: Path = Path("/data")
    db_busy_timeout_ms: int = Field(default=5000, ge=100, le=120_000)

    # -- Authentication ---------------------------------------------------
    service_api_token: str = ""
    worker_token: str = ""

    # -- Workflow ---------------------------------------------------------
    simulation_platform: str = "CUDA"
    allow_pdb_download: bool = True
    pdb_download_timeout_seconds: float = Field(default=30.0, gt=0, le=120)

    # -- Upload and job limits -------------------------------------------
    max_upload_bytes: int = Field(default=50 * MIB, ge=1)
    max_job_upload_bytes: int = Field(default=100 * MIB, ge=1)
    max_ligands: int = Field(default=20, ge=1, le=100)
    max_equilibration_stages: int = Field(default=10, ge=1, le=50)
    max_steps_per_stage: int = Field(default=50_000_000, ge=1)
    max_total_steps: int = Field(default=200_000_000, ge=1)
    max_queued_jobs_per_owner: int = Field(default=5, ge=1, le=1000)

    # -- Storage operations ----------------------------------------------
    min_free_disk_bytes: int = Field(default=512 * MIB, ge=0)
    retention_days: int = Field(default=0, ge=0, le=3650)
    orphan_workspace_hours: int = Field(default=24, ge=1, le=720)

    # -- Streaming and logs ----------------------------------------------
    event_stream_poll_seconds: float = Field(default=1.0, gt=0, le=30)
    event_stream_heartbeat_seconds: float = Field(default=15.0, gt=0, le=120)
    log_tail_max_bytes: int = Field(default=256 * 1024, ge=1024, le=4 * MIB)
    log_tail_default_lines: int = Field(default=200, ge=1, le=10_000)

    # -- Worker lease -----------------------------------------------------
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    worker_heartbeat_interval_seconds: int = Field(default=10, ge=1, le=60)
    reaper_interval_seconds: int = Field(default=10, ge=1, le=600)

    # -- HTTP -------------------------------------------------------------
    cors_origins: str = ""
    docs_enabled: bool = True
    log_level: str = "INFO"
    rate_limit_requests_per_minute: int = Field(default=120, ge=0, le=100_000)

    @field_validator("data_root")
    @classmethod
    def _absolute_data_root(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings object."""

    return Settings()
