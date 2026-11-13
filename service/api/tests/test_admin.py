"""Cross-account administrator views: jobs, system health, and the audit trail."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from conftest import ADMIN_OWNER_ID, job_payload, upgrade_database

NEW_ACCOUNT = {
    "email": "ada@example.com",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "password": "correct horse battery",
}
PDB = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\n"


def _create_job(client, auth, upload, name: str) -> dict:
    file = upload("complex.pdb").json()
    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"], name=name),
    )
    assert response.status_code == 202, response.text
    return response.json()


def _register(client: TestClient) -> dict:
    response = client.post("/api/v1/users", json=NEW_ACCOUNT)
    assert response.status_code == 201
    return response.json()


def _csrf(client: TestClient) -> dict[str, str]:
    from app.session import CSRF_COOKIE

    return {"X-CSRF-Token": client.cookies[CSRF_COOKIE]}


def test_admin_routes_are_not_open_to_regular_accounts(client, auth, upload) -> None:
    assert client.get("/api/v1/admin/jobs").status_code == 401
    assert client.get("/api/v1/admin/system").status_code == 401
    assert client.get("/api/v1/admin/audit").status_code == 401

    _register(client)

    assert client.get("/api/v1/admin/jobs").status_code == 403
    assert client.get("/api/v1/admin/system").status_code == 403
    assert client.get("/api/v1/admin/audit").status_code == 403


def test_admin_jobs_lists_the_whole_platform_with_owners(client, auth, upload) -> None:
    _create_job(client, auth, upload, "admin job")

    # A second account creates its own job; both show up for the admin.
    _register(client)
    file = client.post(
        "/api/v1/files",
        headers=_csrf(client),
        files={"file": ("complex.pdb", PDB, "chemical/x-pdb")},
    ).json()
    client.post(
        "/api/v1/jobs",
        headers=_csrf(client),
        json=job_payload(file["id"], name="ada's job"),
    )

    response = client.get("/api/v1/admin/jobs", headers=auth)
    assert response.status_code == 200
    payload = response.json()

    owners = {item["owner_email"] for item in payload["items"]}
    names = {item["name"] for item in payload["items"]}
    assert "admin@lattice.local" in owners
    assert NEW_ACCOUNT["email"] in owners
    assert {"admin job", "ada's job"} <= names

    by_name = {item["name"]: item for item in payload["items"]}
    assert by_name["admin job"]["owner_email"] == "admin@lattice.local"
    assert by_name["ada's job"]["owner_email"] == NEW_ACCOUNT["email"]
    assert by_name["admin job"]["owner_first_name"]
    assert isinstance(by_name["admin job"]["stale"], bool)


def test_admin_jobs_can_filter_by_status(client, auth, upload) -> None:
    _create_job(client, auth, upload, "queued-one")

    response = client.get("/api/v1/admin/jobs?status=queued", headers=auth)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "queued"

    response = client.get("/api/v1/admin/jobs?status=failed", headers=auth)
    assert response.json()["items"] == []

    response = client.get("/api/v1/admin/jobs?status=not-a-status", headers=auth)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_status"


def test_admin_system_reports_the_platform(client, auth, upload) -> None:
    _create_job(client, auth, upload, "system-health-target")

    response = client.get("/api/v1/admin/system", headers=auth)
    assert response.status_code == 200
    payload = response.json()

    assert payload["database"]["reachable"] is True
    assert payload["database"]["migration"] == "0009"
    assert payload["database"]["jobs"] >= 1
    assert payload["database"]["users"] >= 1

    assert payload["data_root"]["free_bytes"] > 0
    assert payload["data_root"]["min_free_bytes"] > 0
    assert payload["data_root"]["users_bytes"] >= 0

    assert isinstance(payload["workers"], list)
    assert isinstance(payload["queue_counts"], dict)
    assert payload["queue_counts"].get("queued", 0) >= 1


def test_admin_audit_lists_the_platform_history(client, auth, upload) -> None:
    _create_job(client, auth, upload, "audited job")

    response = client.get("/api/v1/admin/audit", headers=auth)
    assert response.status_code == 200
    payload = response.json()

    actions = [item["action"] for item in payload["items"]]
    assert "job.create" in actions

    # The owner join works: rows have an email.
    created = [item for item in payload["items"] if item["action"] == "job.create"]
    assert created[0]["owner_email"] == "admin@lattice.local"


def test_admin_audit_filters_by_action(client, auth, upload) -> None:
    _create_job(client, auth, upload, "audited job")

    response = client.get("/api/v1/admin/audit?action=job.create", headers=auth)
    assert response.status_code == 200
    assert all(item["action"] == "job.create" for item in response.json()["items"])

    response = client.get("/api/v1/admin/audit?action=user.register", headers=auth)
    assert response.json()["items"] == []


def test_admin_audit_pages_backwards(client, auth, upload) -> None:
    for name in ("job-1", "job-2", "job-3"):
        _create_job(client, auth, upload, name)

    first = client.get("/api/v1/admin/audit?limit=2", headers=auth).json()
    assert len(first["items"]) == 2
    cursor = first["next_cursor"]
    assert cursor is not None

    second = client.get(
        f"/api/v1/admin/audit?limit=2&cursor={cursor}", headers=auth
    ).json()
    assert len(second["items"]) >= 1

    ids = [item["id"] for item in first["items"]] + [
        item["id"] for item in second["items"]
    ]
    assert len(set(ids)) == len(ids)


def test_admin_audit_rejects_a_bad_cursor(client, auth) -> None:
    response = client.get("/api/v1/admin/audit?cursor=garbage", headers=auth)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"
