"""Tests for system-preparation: membrane embedding endpoints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.main import create_app
from app.settings import Settings

TEST_TOKEN = "test-service-token"
TEST_WEB_PASSWORD = "test-web-password"
TEST_SESSION_SECRET = "test-session-secret"


def _settings(tmp_path, packmol_path: str = "") -> Settings:
    data_root = tmp_path / "data"
    data_root.mkdir()
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        data_root=data_root,
        service_api_token=TEST_TOKEN,
        worker_token="test-worker-token",
        web_password=TEST_WEB_PASSWORD,
        web_session_secret=TEST_SESSION_SECRET,
        web_cookie_secure=False,
        allow_pdb_download=False,
        simulation_platform="CPU",
        packmol_path=packmol_path,
    )


def _client(tmp_path, packmol_path: str = ""):
    from alembic import command
    from alembic.config import Config

    API_DIR = Path(__file__).resolve().parents[1]
    settings = _settings(tmp_path, packmol_path)
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    app = create_app(settings)
    from fastapi.testclient import TestClient

    return TestClient(app), settings


def test_membrane_embed_requires_packmol_path(tmp_path):
    """Without PACKMOL_PATH, the endpoint returns 503."""
    client, _ = _client(tmp_path, packmol_path="")
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "POPC",
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "prep_not_configured"


def test_membrane_embed_queues_job(tmp_path):
    """With PACKMOL_PATH set, the endpoint queues a job and returns 200."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "POPC",
            "box_padding_nm": 1.5,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert "prep_job_id" in body
    assert body["embedded_pdb_file_id"] is None
    assert body["topology_file_id"] is None


def test_membrane_embed_missing_file(tmp_path):
    """Referencing a nonexistent file returns 400."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": "00000000-0000-0000-0000-000000000000",
            "lipid": "POPC",
        },
    )
    assert response.status_code == 404


def test_membrane_embed_polling_and_list(tmp_path):
    """Job status can be polled and prep jobs can be listed."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")

    # Upload a valid PDB file
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    # Queue the embed
    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "POPC",
        },
    )
    assert response.status_code == 200
    prep_job_id = response.json()["prep_job_id"]

    # Poll status - job stays queued until a worker claims it
    status = client.get(
        f"/api/v1/prep/jobs/{prep_job_id}",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "queued"

    # List prep jobs
    listed = client.get(
        "/api/v1/prep/jobs",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert listed.status_code == 200
    jobs = listed.json()
    assert any(job["id"] == prep_job_id for job in jobs)


def test_membrane_embed_invalid_lipid(tmp_path):
    """An invalid lipid type is rejected by the schema."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "NOT_A_LIPID",
        },
    )
    assert response.status_code == 422


def test_membrane_embed_requires_auth(tmp_path):
    """The endpoint requires authentication."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    response = client.post(
        "/api/v1/prep/membrane",
        json={"protein_file_id": "abc", "lipid": "POPC"},
    )
    assert response.status_code == 401


def test_prep_job_requires_auth(tmp_path):
    """Getting prep job status requires authentication."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    response = client.get("/api/v1/prep/jobs/some-id")
    assert response.status_code == 401


def test_capabilities_shows_prep_workflows(tmp_path):
    """Capabilities includes prep workflow info."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    response = client.get(
        "/api/v1/capabilities",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "prep_workflows" in body
    assert body["prep_workflows"]["membrane_embed"]["enabled"] is True
    assert "POPC" in body["prep_workflows"]["membrane_embed"]["lipids"]


def test_capabilities_prep_disabled_without_packmol(tmp_path):
    """Prep workflows report disabled when packmol is not configured."""
    client, _ = _client(tmp_path, packmol_path="")
    response = client.get(
        "/api/v1/capabilities",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["prep_workflows"]["membrane_embed"]["enabled"] is False


def test_prep_job_cancel_queued(tmp_path):
    """A queued prep job can be canceled."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "POPC",
        },
    )
    assert response.status_code == 200
    prep_job_id = response.json()["prep_job_id"]

    # Cancel the queued job
    cancel = client.post(
        f"/api/v1/prep/jobs/{prep_job_id}/cancel",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "canceled"

    # Verify status is canceled
    status = client.get(
        f"/api/v1/prep/jobs/{prep_job_id}",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert status.json()["status"] == "canceled"


def test_prep_job_cancel_terminal(tmp_path):
    """Canceling a terminal prep job returns its current status."""
    client, _ = _client(tmp_path, packmol_path="/usr/bin/packmol-memgen")
    upload = client.post(
        "/api/v1/files",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    file_id = upload.json()["id"]

    response = client.post(
        "/api/v1/prep/membrane",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        json={
            "protein_file_id": file_id,
            "lipid": "POPC",
        },
    )
    prep_job_id = response.json()["prep_job_id"]

    # Cancel twice - second time should return current status
    cancel1 = client.post(
        f"/api/v1/prep/jobs/{prep_job_id}/cancel",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert cancel1.json()["status"] == "canceled"

    cancel2 = client.post(
        f"/api/v1/prep/jobs/{prep_job_id}/cancel",
        headers={"Authorization": f"Bearer {TEST_TOKEN}"},
    )
    assert cancel2.json()["status"] == "canceled"
