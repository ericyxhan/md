"""Health, readiness, and capability tests."""

from __future__ import annotations

from pathlib import Path


def _expected_migration_head() -> str:
    """The newest Alembic revision in this checkout.

    Derived from the migration files rather than hardcoded, so adding a
    migration does not break the readiness check.
    """
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    revisions: dict[str, str | None] = {}
    for path in sorted(versions.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        revision = None
        down_revision = None
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("revision:"):
                revision = stripped.split("=", 1)[1].strip().strip("'\"")
            elif stripped.startswith("down_revision:"):
                down_revision = stripped.split("=", 1)[1].strip().strip("'\"")
        if revision:
            revisions[revision] = down_revision

    # The head is the revision nothing else points at.
    parents = {v for v in revisions.values() if v}
    heads = [rev for rev in revisions if rev not in parents]
    assert len(heads) == 1, f"expected exactly one migration head, got {heads}"
    return heads[0]


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
    assert body["checks"]["migrations"] == _expected_migration_head()
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
