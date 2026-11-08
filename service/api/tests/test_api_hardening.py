"""Phase 8 hardening: request IDs, rate limits, audit trail, docs policy."""

from __future__ import annotations

import io
import json
import logging

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import observability
from app.main import create_app
from app.models import AuditEvent
from app.settings import Settings
from conftest import TEST_TOKEN, job_payload, upgrade_database


def test_request_id_is_returned_and_sanitized(client, auth) -> None:
    supplied = client.get(
        "/api/v1/capabilities",
        headers={**auth, "X-Request-ID": "client-request-123"},
    )
    assert supplied.status_code == 200
    assert supplied.headers["X-Request-ID"] == "client-request-123"

    generated = client.get("/api/v1/capabilities", headers=auth)
    assert generated.status_code == 200
    assert generated.headers["X-Request-ID"].startswith("req_")

    invalid = client.get(
        "/api/v1/capabilities",
        headers={**auth, "X-Request-ID": "not valid"},
    )
    assert invalid.status_code == 200
    assert invalid.headers["X-Request-ID"].startswith("req_")
    assert invalid.headers["X-Request-ID"] != "not valid"


def test_health_receives_request_id(client) -> None:
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.headers["X-Request-ID"].startswith("req_")


def test_rate_limit_returns_retry_after_and_exempts_health(
    settings: Settings,
) -> None:
    settings.rate_limit_requests_per_minute = 2
    upgrade_database(settings.database_url)
    app = create_app(settings)
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    with TestClient(app) as client:
        assert (
            client.get("/api/v1/capabilities", headers=headers).status_code
            == 200
        )
        assert client.get("/api/v1/jobs", headers=headers).status_code == 200

        limited = client.get("/api/v1/jobs", headers=headers)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limit_exceeded"
        assert int(limited.headers["Retry-After"]) >= 1
        assert limited.headers["X-Request-ID"].startswith("req_")

        # Health checks and internal worker traffic are not rate limited.
        assert client.get("/healthz").status_code == 200


def test_job_mutations_write_audit_events(client, app, auth, upload) -> None:
    file = upload("complex.pdb").json()
    created = client.post(
        "/api/v1/jobs", headers=auth, json=job_payload(file["id"])
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]

    with app.state.session_factory() as session:
        rows = list(
            session.scalars(
                select(AuditEvent).order_by(AuditEvent.id.asc())
            ).all()
        )
    assert [row.action for row in rows] == ["job.create"]
    assert rows[0].owner_id == "local"
    assert rows[0].target_type == "job"
    assert rows[0].target_id == job_id
    assert rows[0].outcome == "accepted"
    assert rows[0].request_id is not None
    assert rows[0].request_id.startswith("req_")
    assert rows[0].remote_addr is not None

    assert (
        client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/jobs/{job_id}/retry",
            headers=auth,
            json={"mode": "restart"},
        ).status_code
        == 200
    )

    with app.state.session_factory() as session:
        rows = list(
            session.scalars(
                select(AuditEvent).order_by(AuditEvent.id.asc())
            ).all()
        )
    assert [row.action for row in rows] == [
        "job.create",
        "job.cancel",
        "job.retry",
    ]
    assert rows[1].outcome == "canceled"
    assert rows[2].outcome == "queued"
    assert rows[2].details_json is not None
    assert json.loads(rows[2].details_json)["mode"] == "restart"


def test_docs_can_be_disabled(settings: Settings) -> None:
    settings.docs_enabled = False
    upgrade_database(settings.database_url)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/healthz").status_code == 200


def test_structured_log_contains_request_id_and_safe_fields() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(observability.JsonFormatter())
    logger = logging.getLogger(observability.LOGGER_NAME)
    logger.addHandler(handler)
    token = observability.request_id_var.set("req_test")
    try:
        observability.log_event(
            "test.event",
            job_id="job-1",
            stage="production",
            token=None,
        )
    finally:
        observability.request_id_var.reset(token)
        logger.removeHandler(handler)

    payload = json.loads(stream.getvalue())
    assert payload["event"] == "test.event"
    assert payload["request_id"] == "req_test"
    assert payload["job_id"] == "job-1"
    assert payload["stage"] == "production"
    assert "token" not in payload


def test_request_logs_exclude_tokens_headers_and_query_strings(
    client, auth
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(observability.JsonFormatter())
    logger = logging.getLogger(observability.LOGGER_NAME)
    logger.addHandler(handler)
    try:
        response = client.get(
            "/api/v1/jobs?status=queued", headers=auth
        )
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 200
    text = stream.getvalue()
    assert TEST_TOKEN not in text
    assert "Authorization" not in text
    assert "status=queued" not in text

    records = [
        json.loads(line) for line in text.splitlines() if line.strip()
    ]
    completed = next(
        record
        for record in records
        if record.get("event") == "request.completed"
    )
    assert completed["path"] == "/api/v1/jobs"
    assert completed["status_code"] == 200
    assert completed["request_id"].startswith("req_")


def test_denied_authentication_is_logged_without_database_write(
    client, app
) -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(observability.JsonFormatter())
    logger = logging.getLogger(observability.LOGGER_NAME)
    logger.addHandler(handler)
    try:
        response = client.get(
            "/api/v1/jobs",
            headers={"Authorization": "Bearer wrong-token"},
        )
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 401
    text = stream.getvalue()
    assert "auth.denied" in text
    assert "wrong-token" not in text

    with app.state.session_factory() as session:
        assert session.scalars(select(AuditEvent)).all() == []
