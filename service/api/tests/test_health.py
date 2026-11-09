"""Health, readiness, and capability tests."""

from __future__ import annotations


def test_healthz_needs_no_auth(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_checks_database_and_storage(client) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["migrations"] == "0004"
    assert body["checks"]["data_root"] == "ok"


def test_capabilities_publishes_limits(client, auth) -> None:
    response = client.get("/api/v1/capabilities", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert "langevin_middle" in body["integrators"]
    assert "monte_carlo" in body["barostats"]
    assert body["limits"]["max_upload_bytes"] == 50 * 1024 * 1024
    assert body["limits"]["rate_limit_requests_per_minute"] == 120
    assert body["pdb_download_enabled"] is False
    assert body["simulation_platform"] == "CPU"
