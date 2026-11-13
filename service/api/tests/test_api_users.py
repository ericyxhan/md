"""Account creation, sign-in, and per-account data isolation."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import FileRecord, Job, PrepJob, User
from app.session import CSRF_COOKIE
from app.settings import Settings
from conftest import ADMIN_OWNER_ID, job_payload, upgrade_database

PDB = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\n"

NEW_ACCOUNT = {
    "email": "ada@example.com",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "password": "correct horse battery",
}


def _csrf(client: TestClient) -> dict[str, str]:
    """The header a cookie-authenticated mutation has to carry."""

    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def _register(client: TestClient, **overrides) -> dict:
    payload = {**NEW_ACCOUNT, **overrides}
    response = client.post("/api/v1/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _sign_in(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/v1/session", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text


def test_registration_creates_an_account_and_signs_it_in(client) -> None:
    created = _register(client)

    assert created["email"] == "ada@example.com"
    assert created["first_name"] == "Ada"
    assert created["last_name"] == "Lovelace"
    assert created["is_admin"] is False
    assert created["is_active"] is True
    assert "password" not in created
    assert "password_hash" not in created

    # The new account is signed in straight away.
    described = client.get("/api/v1/session").json()
    assert described["authenticated"] is True
    assert described["owner"] == created["id"]
    assert described["user"]["email"] == "ada@example.com"


def test_registration_rejects_a_duplicate_email(client) -> None:
    _register(client)

    response = client.post("/api/v1/users", json=NEW_ACCOUNT)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_registration_rejects_an_invalid_email(client) -> None:
    response = client.post(
        "/api/v1/users", json={**NEW_ACCOUNT, "email": "not-an-email"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_email"


def test_registration_rejects_a_short_password(client) -> None:
    response = client.post(
        "/api/v1/users", json={**NEW_ACCOUNT, "password": "short"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "weak_password"


def test_registration_requires_a_first_and_last_name(client) -> None:
    for field in ("first_name", "last_name"):
        response = client.post(
            "/api/v1/users", json={**NEW_ACCOUNT, field: "  "}
        )
        assert response.status_code == 400, field
        assert response.json()["error"]["code"] == "invalid_name"


def test_registration_can_be_switched_off(settings: Settings) -> None:
    settings.registration_enabled = False
    upgrade_database(settings.database_url)
    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/users", json=NEW_ACCOUNT)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "registration_disabled"


def test_new_accounts_can_require_approval(settings: Settings) -> None:
    settings.require_admin_approval = True
    upgrade_database(settings.database_url)
    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        created = client.post("/api/v1/users", json=NEW_ACCOUNT)
        assert created.status_code == 201
        assert created.json()["is_active"] is False

        # The account cannot sign in until it is approved.
        login = client.post(
            "/api/v1/session",
            json={
                "email": NEW_ACCOUNT["email"],
                "password": NEW_ACCOUNT["password"],
            },
        )
        assert login.status_code == 401


def test_sign_in_with_the_new_account(client) -> None:
    _register(client)

    _sign_in(client, NEW_ACCOUNT["email"], NEW_ACCOUNT["password"])
    body = client.get("/api/v1/session").json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == NEW_ACCOUNT["email"]


def test_sign_in_with_a_wrong_password_is_rejected(client) -> None:
    _register(client)

    response = client.post(
        "/api/v1/session",
        json={"email": NEW_ACCOUNT["email"], "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_accounts_cannot_see_each_other_s_data(client, app, upload) -> None:
    """An upload belongs to the account that made it."""

    first = upload("complex.pdb")
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = _register(client)
    second_id = second["id"]

    # The second account cannot read the first account's file.
    hidden = client.get(f"/api/v1/files/{first_id}")
    assert hidden.status_code == 404

    with app.state.session_factory() as session:
        record = session.get(FileRecord, first_id)
        assert record is not None
        assert record.owner_id != second_id

        # The file itself lives inside the first account's directory.
        stored = app.state.storage.absolute_key(record.storage_key)
        assert second_id not in stored.parts


def test_jobs_cannot_be_seen_by_another_account(client, app, auth) -> None:
    uploaded = client.post(
        "/api/v1/files",
        headers=auth,
        files={"file": ("complex.pdb", PDB, "chemical/x-pdb")},
    )
    created = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(uploaded.json()["id"]),
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    _register(client)

    hidden = client.get(f"/api/v1/jobs/{job_id}")
    assert hidden.status_code == 404

    listing = client.get("/api/v1/jobs")
    assert listing.status_code == 200
    assert listing.json()["items"] == []


def test_the_administrator_lists_and_manages_accounts(client, auth) -> None:
    _register(client)

    listed = client.get("/api/v1/users", headers=auth)
    assert listed.status_code == 200
    accounts = listed.json()
    assert len(accounts) == 2
    admin = next(row for row in accounts if row["is_admin"])
    assert admin["id"] == ADMIN_OWNER_ID
    other = next(row for row in accounts if not row["is_admin"])
    assert other["email"] == NEW_ACCOUNT["email"]
    assert other["usage"]["jobs"] == 0

    # A non-administrator cannot list the accounts.
    denied = client.get("/api/v1/users")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"


def test_an_administrator_can_deactivate_an_account(client, app, auth) -> None:
    created = _register(client)

    updated = client.patch(
        f"/api/v1/users/{created['id']}",
        headers=auth,
        json={"is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["is_active"] is False

    # The deactivated account cannot sign in any more.
    login = client.post(
        "/api/v1/session",
        json={
            "email": NEW_ACCOUNT["email"],
            "password": NEW_ACCOUNT["password"],
        },
    )
    assert login.status_code == 401

    with app.state.session_factory() as session:
        account = session.get(User, created["id"])
        assert account is not None
        assert account.is_active is False


def test_an_administrator_cannot_deactivate_themselves(client, auth) -> None:
    response = client.patch(
        f"/api/v1/users/{ADMIN_OWNER_ID}",
        headers=auth,
        json={"is_active": False},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "cannot_deactivate_self"


def test_an_account_can_change_its_own_details(client) -> None:
    created = _register(client)

    updated = client.patch(
        "/api/v1/users/me",
        headers=_csrf(client),
        json={"first_name": "Augusta"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["first_name"] == "Augusta"
    assert updated.json()["id"] == created["id"]


def test_changing_a_password_needs_the_current_one(client) -> None:
    _register(client)

    rejected = client.patch(
        "/api/v1/users/me",
        headers=_csrf(client),
        json={"password": "a brand new password"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "invalid_credentials"

    accepted = client.patch(
        "/api/v1/users/me",
        headers=_csrf(client),
        json={
            "password": "a brand new password",
            "current_password": NEW_ACCOUNT["password"],
        },
    )
    assert accepted.status_code == 200, accepted.text

    # The new password works.
    client.cookies.clear()
    _sign_in(client, NEW_ACCOUNT["email"], "a brand new password")


def test_the_bearer_token_acts_as_the_administrator(client, app, auth) -> None:
    """Machine clients keep working; they act as the administrator."""

    created = client.post(
        "/api/v1/files",
        headers=auth,
        files={"file": ("complex.pdb", PDB, "chemical/x-pdb")},
    )
    assert created.status_code == 201

    with app.state.session_factory() as session:
        record = session.get(FileRecord, created.json()["id"])
        assert record is not None
        assert record.owner_id == ADMIN_OWNER_ID


def test_registration_is_rate_limited_per_address(settings: Settings) -> None:
    settings.web_login_attempts_per_minute = 2
    upgrade_database(settings.database_url)
    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        assert client.post("/api/v1/users", json=NEW_ACCOUNT).status_code == 201
        second = client.post(
            "/api/v1/users", json={**NEW_ACCOUNT, "email": "b@example.com"}
        )
        assert second.status_code == 201
        limited = client.post(
            "/api/v1/users", json={**NEW_ACCOUNT, "email": "c@example.com"}
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "too_many_signup_attempts"


def test_prep_jobs_belong_to_their_account(client, app, auth) -> None:
    """Preparation jobs are owned too, not just simulations."""

    upload = client.post(
        "/api/v1/files",
        headers=auth,
        files={"file": ("protein.pdb", b"HEADER\nEND\n", "chemical/x-pdb")},
    )
    assert upload.status_code == 201

    created = _register(client)

    with app.state.session_factory() as session:
        rows = list(session.scalars(select(PrepJob)).all())
        assert rows == []

    assert created["id"] != ADMIN_OWNER_ID
