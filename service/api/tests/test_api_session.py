"""Browser session authentication and CSRF enforcement."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.session import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    decode_session,
    encode_session,
    hash_password,
    verify_password,
)
from app.settings import Settings
from conftest import (
    TEST_SESSION_SECRET,
    TEST_WEB_PASSWORD,
    job_payload,
    upgrade_database,
)

PDB = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\n"


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/session", json={"password": TEST_WEB_PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert response.json()["authenticated"] is True
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf
    return csrf


def test_login_sets_httponly_session_and_readable_csrf(client) -> None:
    csrf = _login(client)

    session_cookie = client.cookies.get(SESSION_COOKIE)
    assert session_cookie
    assert client.cookies.get(CSRF_COOKIE) == csrf

    described = client.get("/api/v1/session")
    assert described.status_code == 200
    body = described.json()
    assert body["authenticated"] is True
    assert body["owner"] == "local"
    assert body["auth_method"] == "cookie"

    # The session cookie is enough for read requests; no bearer token needed.
    assert client.get("/api/v1/capabilities").status_code == 200


def test_unknown_session_is_reported_without_error(client) -> None:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "owner": None,
                               "issued_at": None, "expires_at": None,
                               "auth_method": None}


def test_bad_password_is_rejected_and_sets_no_cookie(client) -> None:
    response = client.post(
        "/api/v1/session", json={"password": "not-the-password"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert client.cookies.get(SESSION_COOKIE) is None


def test_cookie_mutations_require_csrf_and_csrf_allows_them(
    client, upload
) -> None:
    csrf = _login(client)

    missing = client.post(
        "/api/v1/files",
        files={"file": ("complex.pdb", PDB, "chemical/x-pdb")},
    )
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"

    uploaded = client.post(
        "/api/v1/files",
        headers={"X-CSRF-Token": csrf},
        files={"file": ("complex.pdb", PDB, "chemical/x-pdb")},
    )
    assert uploaded.status_code == 201, uploaded.text

    created = client.post(
        "/api/v1/jobs",
        headers={"X-CSRF-Token": csrf},
        json=job_payload(uploaded.json()["id"]),
    )
    assert created.status_code == 202, created.text


def test_bearer_requests_still_work_without_csrf(client, auth, upload) -> None:
    uploaded = upload("complex.pdb")
    assert uploaded.status_code == 201
    created = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(uploaded.json()["id"])
    )
    assert created.status_code == 202, created.text


def test_logout_clears_session_and_requires_csrf_when_signed_in(
    client,
) -> None:
    csrf = _login(client)

    blocked = client.post("/api/v1/session/logout")
    assert blocked.status_code == 403

    logged_out = client.post(
        "/api/v1/session/logout", headers={"X-CSRF-Token": csrf}
    )
    assert logged_out.status_code == 204
    assert client.get("/api/v1/capabilities").status_code == 401

    # Logging out again is harmless.
    assert client.post("/api/v1/session/logout").status_code == 204


def test_login_is_rate_limited(settings: Settings) -> None:
    settings.web_login_attempts_per_minute = 2
    upgrade_database(settings.database_url)
    app = create_app(settings)

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/session", json={"password": "wrong"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/session", json={"password": "wrong"}
            ).status_code
            == 401
        )
        limited = client.post(
            "/api/v1/session", json={"password": TEST_WEB_PASSWORD}
        )
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "too_many_login_attempts"
        assert int(limited.headers["Retry-After"]) >= 1


def test_session_routes_are_unavailable_without_configuration(
    settings: Settings,
) -> None:
    settings.web_password = ""
    settings.web_password_hash = ""
    upgrade_database(settings.database_url)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/session", json={"password": "anything"}
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "session_not_configured"


def test_signed_session_round_trip_and_tamper_rejection() -> None:
    token, session = encode_session(
        TEST_SESSION_SECRET, "local", ttl_seconds=600, now=1_700_000_000
    )
    decoded = decode_session(
        TEST_SESSION_SECRET, token, now=1_700_000_100
    )
    assert decoded == session
    assert decode_session(TEST_SESSION_SECRET, token, now=1_700_001_000) is None
    assert decode_session("other-secret", token, now=1_700_000_100) is None
    assert decode_session(TEST_SESSION_SECRET, token + "x", now=1_700_000_100) is None


def test_scrypt_password_hash_verification(settings: Settings) -> None:
    settings.web_password = ""
    settings.web_password_hash = hash_password("correct horse battery staple")
    assert verify_password(settings, "correct horse battery staple") is True
    assert verify_password(settings, "wrong") is False
    assert verify_password(settings, "") is False


@pytest.mark.parametrize("cookie_name", [SESSION_COOKIE, CSRF_COOKIE])
def test_login_cookie_attributes(client, cookie_name: str) -> None:
    response = client.post(
        "/api/v1/session", json={"password": TEST_WEB_PASSWORD}
    )
    header = response.headers.get("set-cookie", "")
    assert cookie_name in header or client.cookies.get(cookie_name)
