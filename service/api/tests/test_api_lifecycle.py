"""Cancellation, retry, queue ordering, and lease reaper tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import select

from app.models import Job, JobEvent
from app.schemas_internal import ClaimRequest
from app.services.lifecycle import claim as claim_job
from app.services.reaper import reap_expired_leases
from app.settings import Settings
from app.timeutils import to_iso, utcnow
from conftest import job_payload

WORKER = {"worker_id": "gpu-0"}


def _create_job(client, auth, upload, name: str = "job", **overrides) -> dict:
    file = upload("complex.pdb").json()
    payload = job_payload(file["id"], **overrides)
    payload["name"] = name
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def _claim(client, worker_auth, worker: dict | None = None):
    return client.post(
        "/internal/v1/jobs/claim",
        headers=worker_auth,
        json=worker or WORKER,
    )


def _finish(client, worker_auth, job_id: str, run_token: str, status: str):
    response = client.post(
        f"/internal/v1/jobs/{job_id}/finish",
        headers=worker_auth,
        json={
            "run_token": run_token,
            "status": status,
            "exit_code": 0 if status == "completed" else 1,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_cancel_queued_job_without_a_worker(
    client, app, auth, worker_auth, upload
) -> None:
    job = _create_job(client, auth, upload)

    response = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", headers=auth
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "canceled"
    assert body["queue_position"] is None
    assert body["completed_at"] is not None

    assert _claim(client, worker_auth).status_code == 204

    events = client.get(
        f"/api/v1/jobs/{job['id']}/events", headers=auth
    ).json()
    assert [event["type"] for event in events][-1] == "canceled"

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.cancel_requested is True


def test_cancel_active_job_is_acknowledged_by_worker(
    client, app, auth, worker_auth, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth).json()

    response = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "canceling"

    # Canceling is idempotent and does not append duplicate events.
    again = client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=auth)
    assert again.status_code == 200
    assert again.json()["status"] == "canceling"

    heartbeat = client.post(
        "/internal/v1/workers/heartbeat",
        headers=worker_auth,
        json={
            "worker_id": "gpu-0",
            "hostname": "md-gpu-1",
            "status": "online",
            "current_job_id": job["id"],
            "run_token": claimed["run_token"],
        },
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["cancel_requested"] is True

    progress = client.post(
        f"/internal/v1/jobs/{job['id']}/progress",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "phase": "simulating",
        },
    )
    assert progress.status_code == 200
    assert progress.json()["cancel_requested"] is True

    finished = _finish(
        client, worker_auth, job["id"], claimed["run_token"], "canceled"
    )
    assert finished == {"status": "canceled"}

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "canceled"

    with app.state.session_factory() as session:
        types = [
            event.type
            for event in session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id == job["id"])
                .order_by(JobEvent.id)
            )
        ]
        assert types.count("cancel_requested") == 1
        assert types[-1] == "canceled"


def test_cancel_terminal_job_is_rejected(
    client, auth, worker_auth, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth).json()
    _finish(client, worker_auth, job["id"], claimed["run_token"], "completed")

    response = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", headers=auth
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_retry_resume_and_restart_stage(
    client, app, auth, worker_auth, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth).json()

    # Minimization completes, equilibration fails.
    response = client.post(
        f"/internal/v1/jobs/{job['id']}/stage",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "name": "minimization",
            "status": "completed",
            "steps_completed": 0,
            "attempts": 1,
        },
    )
    assert response.status_code == 200
    response = client.post(
        f"/internal/v1/jobs/{job['id']}/stage",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "name": "equil-01",
            "status": "failed",
            "steps_completed": 4,
            "attempts": 2,
            "error": "blew up",
        },
    )
    assert response.status_code == 200
    _finish(client, worker_auth, job["id"], claimed["run_token"], "failed")

    resumed = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "resume"},
    )
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["status"] == "queued"
    assert body["queue_position"] == 1
    assert body["error"] is None
    stages = {stage["name"]: stage for stage in body["stages"]}
    assert stages["minimization"]["status"] == "completed"
    assert stages["equil-01"]["status"] == "pending"
    assert stages["equil-01"]["steps_completed"] == 0
    assert stages["equil-01"]["error"] is None
    assert stages["equil-01"]["attempts"] == 2

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.restart_mode == "resume"
        assert stored.restart_stage is None
        assert stored.cancel_requested is False

    # Claiming again returns the retry mode to the worker.
    claimed_again = _claim(client, worker_auth).json()
    assert claimed_again["job_id"] == job["id"]
    assert claimed_again["restart_mode"] == "resume"
    _finish(
        client,
        worker_auth,
        job["id"],
        claimed_again["run_token"],
        "failed",
    )

    restarted = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "restart_stage", "stage": "equil-01"},
    )
    assert restarted.status_code == 200, restarted.text
    stages = {stage["name"]: stage for stage in restarted.json()["stages"]}
    assert stages["minimization"]["status"] == "completed"
    assert stages["equil-01"]["status"] == "pending"

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.restart_mode == "restart_stage"
        assert stored.restart_stage == "equil-01"

    invalid = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "restart_stage", "stage": "nope"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "invalid_state"

    claimed_again = _claim(client, worker_auth).json()
    _finish(
        client,
        worker_auth,
        job["id"],
        claimed_again["run_token"],
        "completed",
    )

    resume_completed = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "resume"},
    )
    assert resume_completed.status_code == 409
    assert resume_completed.json()["error"]["code"] == "invalid_retry_mode"

    unknown_stage = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "restart_stage", "stage": "nope"},
    )
    assert unknown_stage.status_code == 422
    assert unknown_stage.json()["error"]["code"] == "invalid_stage"

    restart = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "restart"},
    )
    assert restart.status_code == 200, restart.text
    assert {
        stage["name"]: stage["status"] for stage in restart.json()["stages"]
    } == {"minimization": "pending", "equil-01": "pending"}


def test_retry_requests_are_validated(client, auth, upload) -> None:
    job = _create_job(client, auth, upload)

    response = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "restart_stage"},
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "resume", "stage": "equil-01"},
    )
    assert response.status_code == 422

    response = client.post(
        f"/api/v1/jobs/{job['id']}/retry",
        headers=auth,
        json={"mode": "resume"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_claim_order_uses_requeue_time(
    client, auth, worker_auth, upload
) -> None:
    first = _create_job(client, auth, upload, name="first")
    second = _create_job(client, auth, upload, name="second")

    first_claim = _claim(client, worker_auth).json()
    assert first_claim["job_id"] == first["id"]
    _finish(
        client,
        worker_auth,
        first["id"],
        first_claim["run_token"],
        "failed",
    )

    retried = client.post(
        f"/api/v1/jobs/{first['id']}/retry",
        headers=auth,
        json={"mode": "restart"},
    )
    assert retried.status_code == 200
    assert retried.json()["queue_position"] == 2

    # ``second`` was queued before the retry, so it is claimed first.
    second_claim = _claim(client, worker_auth).json()
    assert second_claim["job_id"] == second["id"]

    _finish(
        client,
        worker_auth,
        second["id"],
        second_claim["run_token"],
        "completed",
    )

    first_again = _claim(client, worker_auth).json()
    assert first_again["job_id"] == first["id"]


def test_concurrent_claims_are_serialized(
    client, app, auth, settings: Settings, upload
) -> None:
    first = _create_job(client, auth, upload, name="first")
    second = _create_job(client, auth, upload, name="second")

    def _claim_as(worker_id: str) -> str | None:
        with app.state.session_factory() as session:
            result = claim_job(
                session,
                settings,
                app.state.storage,
                ClaimRequest(worker_id=worker_id),
            )
            return result.job_id if result is not None else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_claim_as, ["gpu-0", "gpu-1"]))

    assert sorted(results) == sorted([first["id"], second["id"]])

    with app.state.session_factory() as session:
        stored = {
            job.id: job
            for job in session.scalars(
                select(Job).where(Job.id.in_([first["id"], second["id"]]))
            )
        }
        assert {job.status for job in stored.values()} == {"claimed"}
        assert {job.worker_id for job in stored.values()} == {"gpu-0", "gpu-1"}


def test_reaper_ignores_jobs_with_a_live_lease(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job = _create_job(client, auth, upload)
    _claim(client, worker_auth)

    assert reap_expired_leases(app.state.session_factory, settings) == 0

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "claimed"


def test_reaper_fails_lost_worker_job(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth).json()

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.lease_expires_at = to_iso(
            utcnow() - timedelta(seconds=120)
        )
        session.commit()

    reaped = reap_expired_leases(app.state.session_factory, settings)
    assert reaped == 1

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "failed"
    assert detail["error"]["code"] == "worker_lost"

    stale = client.post(
        f"/internal/v1/jobs/{job['id']}/progress",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "phase": "simulating",
        },
    )
    assert stale.status_code == 409

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        assert stored.run_token is None
        assert stored.worker_id is None
        assert stored.lease_expires_at is None


def test_reaper_cancels_job_when_cancel_was_requested(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth).json()
    response = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", headers=auth
    )
    assert response.status_code == 200

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.lease_expires_at = to_iso(
            utcnow() - timedelta(seconds=120)
        )
        session.commit()

    assert reap_expired_leases(app.state.session_factory, settings) == 1
    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth).json()
    assert detail["status"] == "canceled"
    assert detail["error"] is None
