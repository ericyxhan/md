"""Disk, queue, retention, and orphan-cleanup tests."""

from __future__ import annotations

import os
import time
from datetime import timedelta

from sqlalchemy import select

from app.models import Artifact, AuditEvent, Job, JobEvent
from app.services.maintenance import (
    cleanup_expired_jobs,
    cleanup_orphan_workspaces,
    disk_free_bytes,
    ensure_disk_capacity,
)
from app.settings import Settings
from app.timeutils import to_iso, utcnow
from conftest import job_payload, job_workspace, owner_root

from app.errors import APIError

WORKER = {"worker_id": "gpu-0"}


def _create_job(client, auth, upload, name: str = "maintenance") -> dict:
    file = upload("complex.pdb").json()
    payload = job_payload(file["id"])
    payload["name"] = name
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def _claim(client, worker_auth, job_id: str) -> dict:
    response = client.post(
        "/internal/v1/jobs/claim", headers=worker_auth, json=WORKER
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job_id
    return body


def test_queue_limit_rejects_new_jobs(client, auth, settings: Settings, upload) -> None:
    settings.max_queued_jobs_per_owner = 1
    _create_job(client, auth, upload)
    file = upload("other.pdb").json()
    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"], name="second"),
    )
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "queue_limit_exceeded"
    assert body["error"]["details"]["limit"] == 1


def test_disk_reserve_rejects_job_without_leaving_a_workspace(
    client, app, auth, settings: Settings, upload
) -> None:
    file = upload("complex.pdb").json()
    settings.min_free_disk_bytes = (
        disk_free_bytes(settings.data_root) + 1024 * 1024 * 1024
    )
    response = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    )
    assert response.status_code == 507
    assert response.json()["error"]["code"] == "insufficient_storage"

    with app.state.session_factory() as session:
        assert session.scalars(select(Job)).all() == []
    jobs_dir = owner_root(settings) / "jobs"
    assert not jobs_dir.exists() or list(jobs_dir.iterdir()) == []


def test_ensure_disk_capacity_raises_api_error(settings: Settings, app) -> None:
    try:
        ensure_disk_capacity(
            settings,
            app.state.storage,
            required_bytes=disk_free_bytes(settings.data_root) + 1,
        )
    except APIError as exc:
        assert exc.status_code == 507
        assert exc.code == "insufficient_storage"
    else:  # pragma: no cover - defensive
        raise AssertionError("expected insufficient_storage")


def test_cleanup_expired_jobs_removes_rows_and_workspace(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth, job["id"])
    root = job_workspace(settings, job["id"])
    artifact_path = root / "outputs" / "stages" / "equil-01" / "trajectory.dcd"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"trajectory")
    finish = client.post(
        f"/internal/v1/jobs/{job['id']}/finish",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "status": "completed",
            "exit_code": 0,
            "artifacts": [
                {
                    "stage_name": "equil-01",
                    "kind": "trajectory",
                    "relative_path": (
                        "outputs/stages/equil-01/trajectory.dcd"
                    ),
                }
            ],
        },
    )
    assert finish.status_code == 200, finish.text

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.completed_at = to_iso(utcnow() - timedelta(days=10))
        session.commit()

    settings.retention_days = 1

    dry = cleanup_expired_jobs(
        app.state.session_factory, app.state.storage, settings, dry_run=True
    )
    assert dry.jobs_removed == 1
    assert dry.bytes_freed >= artifact_path.stat().st_size
    with app.state.session_factory() as session:
        assert session.get(Job, job["id"]) is not None
    assert artifact_path.is_file()

    result = cleanup_expired_jobs(
        app.state.session_factory, app.state.storage, settings
    )
    assert result.jobs_removed == 1
    assert result.bytes_freed >= len(b"trajectory")
    assert not root.exists()

    with app.state.session_factory() as session:
        assert session.get(Job, job["id"]) is None
        assert session.scalars(
            select(Artifact).where(Artifact.job_id == job["id"])
        ).all() == []
        assert session.scalars(
            select(JobEvent).where(JobEvent.job_id == job["id"])
        ).all() == []
        audits = list(
            session.scalars(
                select(AuditEvent)
                .where(
                    AuditEvent.target_type == "job",
                    AuditEvent.target_id == job["id"],
                )
                .order_by(AuditEvent.id.asc())
            ).all()
        )
    assert [row.action for row in audits] == [
        "job.create",
        "job.claim",
        "job.finish",
        "job.retention_delete",
    ]


def test_cleanup_keeps_recent_and_active_jobs(
    client, app, auth, settings: Settings, upload
) -> None:
    recent = _create_job(client, auth, upload, name="recent")
    settings.retention_days = 1
    # A queued job is not terminal and must be left alone.
    result = cleanup_expired_jobs(
        app.state.session_factory, app.state.storage, settings
    )
    assert result.jobs_removed == 0
    assert client.get(
        f"/api/v1/jobs/{recent['id']}", headers=auth
    ).status_code == 200


def test_cleanup_orphan_workspaces(
    client, app, settings: Settings
) -> None:
    orphan = owner_root(settings) / "jobs" / ".abandoned.tmp"
    (orphan / "outputs").mkdir(parents=True)
    (orphan / "outputs" / "big.bin").write_bytes(b"x" * 256)

    partial = owner_root(settings) / "uploads" / "file-id" / "upload.pdb.part"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial")

    old = time.time() - 7200
    os.utime(orphan, (old, old))
    os.utime(partial, (old, old))
    settings.orphan_workspace_hours = 1

    dry = cleanup_orphan_workspaces(
        app.state.storage, settings, dry_run=True
    )
    assert dry.orphan_workspaces_removed == 2
    assert orphan.exists() and partial.exists()

    result = cleanup_orphan_workspaces(app.state.storage, settings)
    assert result.orphan_workspaces_removed == 2
    assert result.orphan_bytes_freed >= 256 + len(b"partial")
    assert not orphan.exists()
    assert not partial.exists()
