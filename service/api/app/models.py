"""SQLAlchemy models for the control plane."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_worker_id", "worker_id"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        Index("ix_jobs_owner_created_at", "owner_id", "created_at"),
        # Created by migration 0005; declared here so the model and the
        # migrated schema agree (otherwise ``alembic --autogenerate`` would
        # propose dropping it).
        Index("ix_jobs_workflow_id", "workflow_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    phase: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)

    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    config_toml: Mapped[str] = mapped_column(Text, nullable=False)
    input_mode: Mapped[str] = mapped_column(String(24), nullable=False)

    restart_mode: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    restart_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    run_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    current_stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    progress_step: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress_total_steps: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    progress_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    progress_updated_at: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )

    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    workflow_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    queued_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    started_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    stages: Mapped[list["JobStage"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobStage.position",
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class Workflow(Base):
    """A named base system (prepared or embedded structure) with derived jobs.

    Workflows group together simulations that share a common input structure,
    for example a membrane-embedded protein and the eight production replicates
    launched from it.  A workflow is created from a completed prep job's output
    file; child jobs reference it through ``workflow_id``.
    """

    __tablename__ = "workflows"
    __table_args__ = (
        Index("ix_workflows_owner_created_at", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class JobStage(Base):
    __tablename__ = "job_stages"
    __table_args__ = (
        UniqueConstraint("job_id", "name", name="uq_job_stages_job_id_name"),
        Index("ix_job_stages_job_position", "job_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    steps_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    steps_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="stages")


class FileRecord(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_owner_id", "owner_id"),
        Index("ix_files_owner_created_at", "owner_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "relative_path", name="uq_artifacts_job_id_relative_path"
        ),
        Index("ix_artifacts_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    job: Mapped[Job] = relationship(back_populates="artifacts")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        Index("ix_job_events_job_id_id", "job_id", "id"),
        # The account-wide activity feed reads the newest events across all
        # jobs; without this index the feed sorts the whole event history.
        Index("ix_job_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    gpu_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gpu_uuid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    current_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_heartbeat_at: Mapped[str] = mapped_column(String(32), nullable=False)
    registered_at: Mapped[str] = mapped_column(String(32), nullable=False)


class AuditEvent(Base):
    """Append-only record of security-relevant control-plane actions.

    Audit rows intentionally have no foreign key to jobs: they must survive
    retention deletion of the job they describe.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_owner_created_at", "owner_id", "created_at"),
        Index("ix_audit_events_action_created_at", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remote_addr: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class PrepJob(Base):
    """System-preparation jobs: membrane embedding, box building, etc.

    Prep jobs are long-running background tasks that transform uploaded
    structures into simulation-ready systems.  Their outputs are registered as
    normal file records so they can be referenced as ``complex_file_id`` in an
    MD job creation request.
    """

    __tablename__ = "prep_jobs"
    __table_args__ = (
        Index("ix_prep_jobs_owner_created_at", "owner_id", "created_at"),
        Index("ix_prep_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="queued"
    )
    run_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_file_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phase: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    progress_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    progress_message: Mapped[Optional[str]] = mapped_column(
        String(1000), nullable=True
    )
    progress_updated_at: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
    completed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    events: Mapped[list["PrepEvent"]] = relationship(
        back_populates="prep_job",
        cascade="all, delete-orphan",
        order_by="PrepEvent.id",
    )


class PrepEvent(Base):
    """Append-only event log for system-preparation jobs.

    Prep jobs (membrane embedding, structure editing) are not MD jobs, so
    their activity cannot live in ``job_events`` — that table is keyed by
    ``jobs.id``.  This table mirrors it for prep jobs so the account-wide
    activity feed can show both.
    """

    __tablename__ = "prep_events"
    __table_args__ = (
        Index("ix_prep_events_prep_job_id_id", "prep_job_id", "id"),
        Index("ix_prep_events_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prep_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("prep_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)

    # The relationship is what makes SQLAlchemy insert the parent row before
    # this one; a bare ForeignKey column is not enough once the database
    # enforces referential integrity.
    prep_job: Mapped["PrepJob"] = relationship(back_populates="events")
