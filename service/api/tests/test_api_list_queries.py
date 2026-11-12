"""Regression tests for the job list query pattern.

Listing jobs used to run one query per job: a lazy load of the job's stages
and a COUNT for its queue position.  A page of twenty jobs cost forty-one
statements.  These tests pin the batched behaviour so it does not come back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.settings import Settings
from conftest import job_payload


@pytest.fixture()
def settings(settings: Settings) -> Settings:
    """Allow enough queued jobs to fill a page."""

    return settings.model_copy(update={"max_queued_jobs_per_owner": 1000})


def _count_statements(app) -> list[str]:
    statements: list[str] = []

    @event.listens_for(app.state.engine, "before_cursor_execute")
    def _record(conn, cursor, statement, params, context, executemany):
        statements.append(" ".join(statement.split()))

    return statements


def test_job_list_uses_a_constant_number_of_queries(
    client, auth, app, upload
) -> None:
    file = upload("complex.pdb").json()
    for index in range(10):
        response = client.post(
            "/api/v1/jobs",
            headers=auth,
            json=job_payload(file["id"], name=f"job {index}"),
        )
        assert response.status_code == 202, response.text

    statements = _count_statements(app)
    response = client.get("/api/v1/jobs", headers=auth)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 10

    # One page query, one query for the stages of the whole page, and one
    # ranked query for the queue positions.
    assert len(statements) <= 4, statements


def test_job_list_reports_queue_positions(
    client, auth, settings, upload
) -> None:
    file = upload("complex.pdb").json()
    for index in range(3):
        response = client.post(
            "/api/v1/jobs",
            headers=auth,
            json=job_payload(file["id"], name=f"job {index}"),
        )
        assert response.status_code == 202, response.text

    items = client.get("/api/v1/jobs", headers=auth).json()["items"]
    positions = sorted(item["queue_position"] for item in items)
    assert positions == [1, 2, 3]


def test_workflow_list_uses_a_constant_number_of_queries(
    client, auth, app, upload
) -> None:
    file = upload("complex.pdb").json()
    for index in range(5):
        response = client.post(
            "/api/v1/workflows",
            headers=auth,
            json={
                "name": f"workflow {index}",
                "source_file_id": file["id"],
                "source_type": "membrane_embed",
            },
        )
        assert response.status_code == 201, response.text

    statements = _count_statements(app)
    response = client.get("/api/v1/workflows", headers=auth)
    assert response.status_code == 200
    assert len(response.json()) == 5

    # One query for the workflows and one grouped query for the child counts.
    assert len(statements) <= 3, statements
