"""Shared pytest fixtures for the service API tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402

TEST_TOKEN = "test-service-token"
WORKER_TOKEN = "test-worker-token"
TEST_WEB_PASSWORD = "test-web-password"
TEST_SESSION_SECRET = "test-session-secret"


def upgrade_database(database_url: str) -> None:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    data_root = tmp_path / "data"
    data_root.mkdir()
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        data_root=data_root,
        service_api_token=TEST_TOKEN,
        worker_token=WORKER_TOKEN,
        web_password=TEST_WEB_PASSWORD,
        web_session_secret=TEST_SESSION_SECRET,
        web_cookie_secure=False,
        allow_pdb_download=False,
        simulation_platform="CPU",
    )


@pytest.fixture()
def app(settings: Settings):
    upgrade_database(settings.database_url)
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture()
def worker_auth() -> dict[str, str]:
    return {"X-Worker-Token": WORKER_TOKEN}


@pytest.fixture()
def upload(client, auth):
    def _upload(
        name: str,
        content: bytes = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\n",
        content_type: str = "chemical/x-pdb",
    ):
        return client.post(
            "/api/v1/files",
            headers=auth,
            files={"file": (name, content, content_type)},
        )

    return _upload


def job_payload(complex_file_id: str, **overrides) -> dict:
    payload = {
        "name": "test job",
        "input": {"mode": "complex", "complex_file_id": complex_file_id},
        "parameterization": {"ph": 7.4},
        "minimization": {"enabled": True},
        "equilibration": [
            {
                "label": "NVT",
                "duration_ps": 0.02,
                "report_interval": 10,
                "trajectory_interval": 10,
                "checkpoint_interval": 10,
                "integrator": {
                    "type": "langevin_middle",
                    "temperature_k": 300.0,
                    "friction_per_ps": 1.0,
                    "timestep_ps": 0.002,
                },
                "barostat": {"type": "none"},
            }
        ],
        "production": {
            "enabled": False,
        },
    }
    payload.update(overrides)
    return payload
