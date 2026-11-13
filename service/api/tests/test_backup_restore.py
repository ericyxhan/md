"""Backup and restore procedure smoke test."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from conftest import ADMIN_OWNER_ID, job_payload, job_workspace


def test_sqlite_backup_and_job_data_restore(
    client, auth, worker_auth, settings, upload, tmp_path: Path
) -> None:
    file = upload("complex.pdb").json()
    completed_response = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    )
    assert completed_response.status_code == 202, completed_response.text
    completed_job = completed_response.json()
    claimed = client.post(
        "/internal/v1/jobs/claim",
        headers=worker_auth,
        json={"worker_id": "gpu-0"},
    ).json()
    assert claimed["job_id"] == completed_job["id"]
    artifact_path = (
        job_workspace(settings, completed_job["id"])
        / "outputs"
        / "stages"
        / "equil-01"
        / "trajectory.dcd"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"trajectory bytes")
    finished = client.post(
        f"/internal/v1/jobs/{completed_job['id']}/finish",
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
    assert finished.status_code == 200, finished.text

    queued_response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"], name="still queued"),
    )
    assert queued_response.status_code == 202, queued_response.text
    queued_job = queued_response.json()

    database_path = Path(
        settings.database_url.removeprefix("sqlite:///")
    )
    backup_path = tmp_path / "backups" / "app.db"
    backup_path.parent.mkdir(parents=True)

    # SQLite's backup API copies a consistent snapshot including WAL state.
    with sqlite3.connect(database_path) as source, sqlite3.connect(
        backup_path
    ) as destination:
        source.backup(destination)

    restored_database = tmp_path / "restore" / "app.db"
    restored_database.parent.mkdir()
    shutil.copy2(backup_path, restored_database)
    restored_data = tmp_path / "restore" / "data"
    shutil.copytree(settings.data_root, restored_data)

    with sqlite3.connect(restored_database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        statuses = dict(
            connection.execute(
                "SELECT id, status FROM jobs WHERE id IN (?, ?)",
                (completed_job["id"], queued_job["id"]),
            ).fetchall()
        )
        artifact_count = connection.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id = ?",
            (completed_job["id"],),
        ).fetchone()[0]
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM audit_events"
        ).fetchone()[0]
    assert statuses == {
        completed_job["id"]: "completed",
        queued_job["id"]: "queued",
    }
    assert artifact_count == 1
    assert audit_count >= 4

    job_root = (
        restored_data
        / "users"
        / ADMIN_OWNER_ID
        / "jobs"
        / completed_job["id"]
    )
    assert (job_root / "config.toml").is_file()
    assert (job_root / "job.json").is_file()
    assert (job_root / "inputs" / "complex.pdb").is_file()
    assert (
        job_root / "outputs" / "stages" / "equil-01" / "trajectory.dcd"
    ).read_bytes() == b"trajectory bytes"

    # The restored database is a normal, openable service database.
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{restored_database}")
    try:
        with engine.connect() as connection:
            status = connection.execute(
                text("SELECT status FROM jobs WHERE id = :job_id"),
                {"job_id": completed_job["id"]},
            ).scalar_one()
    finally:
        engine.dispose()
    assert status == "completed"
