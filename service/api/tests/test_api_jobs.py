"""Public job API tests."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.config_builder import load_workflow_config
from app.models import Job
from app.settings import Settings
from conftest import job_payload


def test_create_list_and_detail(client, auth, settings: Settings, upload) -> None:
    file = upload("complex.pdb").json()

    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"]),
    )
    assert response.status_code == 202, response.text
    job = response.json()

    assert job["status"] == "queued"
    assert job["queue_position"] == 1
    assert job["input_mode"] == "complex"
    assert [stage["name"] for stage in job["stages"]] == [
        "minimization",
        "equil-01",
    ]
    assert job["stages"][1]["steps_target"] == 10
    assert job["error"] is None

    job_root = settings.data_root / "jobs" / job["id"]
    assert (job_root / "config.toml").is_file()
    assert (job_root / "job.json").is_file()
    assert (job_root / "inputs" / "complex.pdb").is_file()

    config = load_workflow_config(job_root / "config.toml")
    assert config.run.platform == "CPU"
    assert config.equilibration[0].steps == 10
    assert config.production is None

    saved = json.loads((job_root / "job.json").read_text())
    assert saved["job_id"] == job["id"]
    assert saved["spec"]["equilibration"][0]["name"] == "equil-01"

    detail = client.get(f"/api/v1/jobs/{job['id']}", headers=auth)
    assert detail.status_code == 200
    assert detail.json()["id"] == job["id"]

    listing = client.get("/api/v1/jobs", headers=auth)
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()["items"]] == [job["id"]]

    by_status = client.get("/api/v1/jobs?status=queued", headers=auth)
    assert len(by_status.json()["items"]) == 1

    empty = client.get("/api/v1/jobs?status=failed", headers=auth)
    assert empty.json()["items"] == []


def test_config_spec_and_events(client, auth, upload) -> None:
    file = upload("complex.pdb").json()
    job = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    ).json()

    config = client.get(f"/api/v1/jobs/{job['id']}/config", headers=auth)
    assert config.status_code == 200
    assert "[run]" in config.text
    assert "output_dir" in config.text

    spec = client.get(f"/api/v1/jobs/{job['id']}/spec", headers=auth)
    assert spec.status_code == 200
    assert spec.json()["equilibration"][0]["steps"] == 10

    events = client.get(f"/api/v1/jobs/{job['id']}/events", headers=auth)
    assert events.status_code == 200
    types = [event["type"] for event in events.json()]
    assert types[:2] == ["created", "queued"]


def test_production_and_stage_names(client, auth, upload) -> None:
    file = upload("complex.pdb").json()
    payload = job_payload(
        file["id"],
        equilibration=[
            {"duration_ps": 0.02, "label": "NVT"},
            {"duration_ps": 0.02, "label": "NPT"},
        ],
        production={
            "enabled": True,
            "duration_ns": 0.001,
            "barostat": {
                "type": "monte_carlo",
                "pressure_bar": 1.0,
                "temperature_k": 300.0,
            },
        },
    )
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    assert [stage["name"] for stage in response.json()["stages"]] == [
        "minimization",
        "equil-01",
        "equil-02",
        "production",
    ]


def test_dry_validation_does_not_create_a_job(
    client, app, auth, upload
) -> None:
    file = upload("complex.pdb").json()
    response = client.post(
        "/api/v1/jobs/validate", headers=auth, json=job_payload(file["id"])
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["plan"]["equilibration"][0]["name"] == "equil-01"
    assert "[run]" in body["config_toml"]

    with app.state.session_factory() as session:
        assert session.scalars(select(Job)).all() == []


def test_unknown_input_file_is_404(client, auth) -> None:
    response = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload("missing-file")
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"


def test_extra_fields_are_rejected(client, auth, upload) -> None:
    file = upload("complex.pdb").json()
    payload = job_payload(file["id"])
    payload["raw_toml"] = "[run]\nplatform = 'CUDA'"
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_stage_duration_is_a_clean_422(client, auth, upload) -> None:
    file = upload("complex.pdb").json()
    payload = job_payload(
        file["id"],
        equilibration=[
            {
                "steps": 10,
                "duration_ps": 1.0,
                "integrator": {"type": "langevin_middle"},
            }
        ],
    )
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "exactly one" in body["error"]["details"]["errors"][0]["msg"]


def test_pdb_download_gate(client, auth) -> None:
    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json={
            "name": "pdb",
            "input": {"mode": "pdb_id", "pdb_id": "7YAE"},
            "equilibration": [{"steps": 10}],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "pdb_download_disabled"


def test_job_upload_total_limit(client, auth, settings: Settings, upload) -> None:
    file = upload("complex.pdb", b"x" * 100).json()
    settings.max_job_upload_bytes = 50
    response = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "job_upload_too_large"


def test_jobs_are_filtered_by_owner(client, app, auth, upload) -> None:
    file = upload("complex.pdb").json()
    job = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    ).json()

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        stored.owner_id = "someone-else"
        session.commit()

    response = client.get(f"/api/v1/jobs/{job['id']}", headers=auth)
    assert response.status_code == 404
    listing = client.get("/api/v1/jobs", headers=auth)
    assert listing.json()["items"] == []
