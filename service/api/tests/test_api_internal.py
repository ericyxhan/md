"""Internal worker protocol tests."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.models import Artifact, Job, JobEvent, Worker
from app.settings import Settings
from conftest import job_payload

WORKER = {"worker_id": "gpu-0", "gpu_uuid": "GPU-1234"}


def _create_job(client, auth, upload, **overrides) -> dict:
    file = upload("complex.pdb").json()
    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"], **overrides),
    )
    assert response.status_code == 202, response.text
    return response.json()


def _claim(client, worker_auth, worker: dict | None = None):
    return client.post(
        "/internal/v1/jobs/claim",
        headers=worker_auth,
        json=worker or WORKER,
    )


def _claimed_job(client, auth, upload, worker_auth) -> tuple[dict, dict]:
    job = _create_job(client, auth, upload)
    response = _claim(client, worker_auth)
    assert response.status_code == 200, response.text
    claimed = response.json()
    assert claimed["job_id"] == job["id"]
    return job, claimed


def _heartbeat(client, worker_auth, claimed: dict, **overrides) -> dict:
    payload = {
        "worker_id": WORKER["worker_id"],
        "hostname": "md-gpu-1",
        "gpu_name": "NVIDIA Test",
        "gpu_uuid": WORKER["gpu_uuid"],
        "version": "0.1.0",
        "status": "online",
        "current_job_id": claimed["job_id"],
        "run_token": claimed["run_token"],
    }
    payload.update(overrides)
    response = client.post(
        "/internal/v1/workers/heartbeat",
        headers=worker_auth,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _progress(client, worker_auth, claimed: dict, **overrides) -> dict:
    payload = {
        "run_token": claimed["run_token"],
        "phase": "simulating",
        "stage": "equil-01",
        "step": 5,
        "total_steps": 10,
        "percent": 50.0,
    }
    payload.update(overrides)
    response = client.post(
        f"/internal/v1/jobs/{claimed['job_id']}/progress",
        headers=worker_auth,
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _stage(client, worker_auth, claimed: dict, **overrides):
    payload = {
        "run_token": claimed["run_token"],
        "name": "equil-01",
        "status": "running",
        "steps_completed": 0,
        "attempts": 1,
    }
    payload.update(overrides)
    return client.post(
        f"/internal/v1/jobs/{claimed['job_id']}/stage",
        headers=worker_auth,
        json=payload,
    )


def _finish(client, worker_auth, claimed: dict, **overrides):
    payload = {
        "run_token": claimed["run_token"],
        "status": "completed",
        "exit_code": 0,
        "artifacts": [],
    }
    payload.update(overrides)
    return client.post(
        f"/internal/v1/jobs/{claimed['job_id']}/finish",
        headers=worker_auth,
        json=payload,
    )


def test_claim_progress_stage_and_finish(
    client,
    app,
    auth,
    worker_auth,
    settings: Settings,
    upload,
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)

    assert claimed["restart_mode"] == "resume"
    assert claimed["restart_stage"] is None
    assert claimed["config_path"].endswith("/config.toml")
    assert claimed["config_path"].startswith(str(settings.data_root))
    assert claimed["job_root"] == str(settings.data_root / "jobs" / job["id"])
    assert [stage["name"] for stage in claimed["stages"]] == [
        "minimization",
        "equil-01",
    ]
    assert claimed["stages"][1]["steps_target"] == 10

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "claimed"
    assert detail["attempt"] == 1
    assert detail["queue_position"] is None

    heartbeat = _heartbeat(client, worker_auth, claimed)
    assert heartbeat["cancel_requested"] is False
    assert heartbeat["lease_expires_at"] is not None

    progress = _progress(client, worker_auth, claimed)
    assert progress["cancel_requested"] is False

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "running"
    assert detail["phase"] == "simulating"
    assert detail["current_stage"] == "equil-01"
    assert detail["progress"]["step"] == 5
    assert detail["progress"]["percent"] == 50.0

    running = _stage(client, worker_auth, claimed)
    assert running.status_code == 200, running.text
    completed = _stage(
        client,
        worker_auth,
        claimed,
        status="completed",
        steps_completed=10,
        manifest_json='{"status": "completed", "steps_completed": 10}',
    )
    assert completed.status_code == 200, completed.text

    with app.state.session_factory() as session:
        stored_job = session.get(Job, job["id"])
        assert stored_job is not None
        equil = next(
            stage
            for stage in stored_job.stages
            if stage.name == "equil-01"
        )
        assert equil.manifest_json is not None
        assert json.loads(equil.manifest_json)["steps_completed"] == 10

    stage_row = next(
        item
        for item in client.get(
            f"/api/v1/jobs/{job['id']}", headers=auth
        ).json()["stages"]
        if item["name"] == "equil-01"
    )
    assert stage_row["status"] == "completed"
    assert stage_row["steps_completed"] == 10
    assert stage_row["completed_at"] is not None

    job_root = settings.data_root / "jobs" / job["id"]
    artifact = job_root / "outputs" / "stages" / "equil-01" / "stage.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"status": "completed"}\n', encoding="utf-8")

    finished = _finish(
        client,
        worker_auth,
        claimed,
        artifacts=[
            {
                "stage_name": "equil-01",
                "kind": "metadata",
                "relative_path": "outputs/stages/equil-01/stage.json",
                "size_bytes": 1,
                "content_type": "application/json",
            }
        ],
    )
    assert finished.status_code == 200, finished.text
    assert finished.json() == {"status": "completed"}

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "completed"
    assert detail["completed_at"] is not None

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.exit_code == 0
        assert stored.worker_id is None
        assert stored.run_token is None
        assert stored.lease_expires_at is None

        artifacts = session.scalars(
            select(Artifact).where(Artifact.job_id == job["id"])
        ).all()
        assert len(artifacts) == 1
        assert artifacts[0].size_bytes == artifact.stat().st_size
        assert artifacts[0].kind == "metadata"

        worker = session.get(Worker, WORKER["worker_id"])
        assert worker is not None
        assert worker.current_job_id is None

    events = client.get(
        f"/api/v1/jobs/{job['id']}/events", headers=auth
    ).json()
    event_types = [event["type"] for event in events]
    assert "claimed" in event_types
    assert "running" in event_types
    assert "phase_changed" in event_types
    assert "stage" in event_types
    assert event_types[-1] == "completed"

    stale = _finish(client, worker_auth, claimed)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_run_token"


def test_internal_routes_are_hidden_from_openapi(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert not any(path.startswith("/internal/") for path in paths)
    assert "/api/v1/jobs/{job_id}/cancel" in paths
    assert "/api/v1/jobs/{job_id}/retry" in paths


def test_claim_returns_204_when_queue_is_empty(client, worker_auth) -> None:
    response = _claim(client, worker_auth)
    assert response.status_code == 204
    assert response.content == b""


def test_internal_routes_require_worker_token(client, auth, upload) -> None:
    job = _create_job(client, auth, upload)
    response = client.post(
        "/internal/v1/jobs/claim",
        headers=auth,
        json=WORKER,
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert job["status"] == "queued"


def test_heartbeat_mismatch_does_not_extend_lease(
    client,
    app,
    auth,
    worker_auth,
    upload,
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        original_lease = stored.lease_expires_at

    mismatch = _heartbeat(
        client,
        worker_auth,
        claimed,
        run_token="00000000-0000-0000-0000-000000000000",
    )
    assert mismatch["cancel_requested"] is False
    assert mismatch["lease_expires_at"] is None

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.lease_expires_at == original_lease

    matched = _heartbeat(client, worker_auth, claimed)
    assert matched["lease_expires_at"] is not None
    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.lease_expires_at == matched["lease_expires_at"]


def test_progress_rejects_stale_token(
    client, auth, worker_auth, upload
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)
    response = client.post(
        f"/internal/v1/jobs/{job['id']}/progress",
        headers=worker_auth,
        json={
            "run_token": "00000000-0000-0000-0000-000000000000",
            "phase": "simulating",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_run_token"


def test_finish_artifact_paths_are_confined(
    client, app, auth, worker_auth, settings: Settings, upload, tmp_path: Path
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)
    job_root = settings.data_root / "jobs" / job["id"]

    traversal = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        artifacts=[
            {
                "kind": "metadata",
                "relative_path": "../escape.json",
            }
        ],
    )
    assert traversal.status_code == 400
    assert traversal.json()["error"]["code"] == "invalid_artifact_path"

    absolute = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        artifacts=[
            {
                "kind": "metadata",
                "relative_path": "/etc/passwd",
            }
        ],
    )
    assert absolute.status_code == 400

    missing = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        artifacts=[
            {
                "kind": "metadata",
                "relative_path": "outputs/missing.json",
            }
        ],
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "artifact_missing"

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = job_root / "outputs" / "link.json"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    symlink = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        artifacts=[
            {
                "kind": "metadata",
                "relative_path": "outputs/link.json",
            }
        ],
    )
    assert symlink.status_code == 400
    assert symlink.json()["error"]["code"] == "invalid_artifact_path"

    bad_stage = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        artifacts=[
            {
                "stage_name": "not-a-stage",
                "kind": "metadata",
                "relative_path": "outputs/link.json",
            }
        ],
    )
    assert bad_stage.status_code == 422
    assert bad_stage.json()["error"]["code"] == "invalid_stage"

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "claimed"

    with app.state.session_factory() as session:
        assert (
            session.scalars(
                select(Artifact).where(Artifact.job_id == job["id"])
            ).all()
            == []
        )


def test_failed_finish_and_stale_updates(
    client, app, auth, worker_auth, upload
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)

    failed = _finish(
        client,
        worker_auth,
        claimed,
        status="failed",
        exit_code=2,
        error_code="stage_failed",
        error_message="Equilibration diverged",
    )
    assert failed.status_code == 200
    assert failed.json() == {"status": "failed"}

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "failed"
    assert detail["error"] == {
        "code": "stage_failed",
        "message": "Equilibration diverged",
    }

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.exit_code == 2

    stale_progress = client.post(
        f"/internal/v1/jobs/{job['id']}/progress",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "phase": "simulating",
        },
    )
    assert stale_progress.status_code == 409

    with app.state.session_factory() as session:
        events = session.scalars(
            select(JobEvent)
            .where(JobEvent.job_id == job["id"])
            .order_by(JobEvent.id)
        ).all()
        assert events[-1].type == "failed"


def test_finish_rejects_unknown_stage(
    client, auth, worker_auth, upload
) -> None:
    _job, claimed = _claimed_job(client, auth, upload, worker_auth)
    response = _stage(
        client,
        worker_auth,
        claimed,
        name="does-not-exist",
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "stage_not_found"


def test_duplicate_artifact_reports_are_upserted(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job, claimed = _claimed_job(client, auth, upload, worker_auth)
    artifact = settings.data_root / "jobs" / job["id"] / "outputs" / "result.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("{}", encoding="utf-8")
    entry = {
        "kind": "metadata",
        "relative_path": "outputs/result.json",
    }

    response = _finish(
        client,
        worker_auth,
        claimed,
        artifacts=[entry, dict(entry)],
    )
    assert response.status_code == 200, response.text

    with app.state.session_factory() as session:
        artifacts = session.scalars(
            select(Artifact).where(Artifact.job_id == job["id"])
        ).all()
        assert len(artifacts) == 1
        assert artifacts[0].size_bytes == artifact.stat().st_size
