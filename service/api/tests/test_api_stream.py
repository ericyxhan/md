"""Server-sent event stream tests."""

from __future__ import annotations

from app.models import Job
from conftest import job_payload


def _create_job(client, auth, upload, name: str = "stream") -> dict:
    file = upload("complex.pdb").json()
    payload = job_payload(file["id"])
    payload["name"] = name
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def _terminal_job(client, auth, upload) -> tuple[dict, list[dict]]:
    job = _create_job(client, auth, upload)
    canceled = client.post(
        f"/api/v1/jobs/{job['id']}/cancel", headers=auth
    )
    assert canceled.status_code == 200
    events = client.get(
        f"/api/v1/jobs/{job['id']}/events", headers=auth
    ).json()
    return job, events


def test_event_stream_for_terminal_job_ends(
    client, auth, upload
) -> None:
    job, events = _terminal_job(client, auth, upload)
    response = client.get(
        f"/api/v1/jobs/{job['id']}/events/stream", headers=auth
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    body = response.text
    assert "event: job" in body
    assert "event: progress" in body
    assert "event: end" in body
    assert '"status":"canceled"' in body
    assert f"id: {events[-1]['id']}" in body
    assert "retry:" not in body


def test_event_stream_resumes_after_last_event_id(
    client, auth, upload
) -> None:
    job, events = _terminal_job(client, auth, upload)
    last = events[-1]

    resumed = client.get(
        f"/api/v1/jobs/{job['id']}/events/stream",
        headers={**auth, "Last-Event-ID": str(last["id"])},
    )
    assert resumed.status_code == 200
    body = resumed.text
    assert "event: job" not in body
    assert "event: progress" in body
    assert "event: end" in body
    assert "created" not in body

    queried = client.get(
        f"/api/v1/jobs/{job['id']}/events/stream?after_id={last['id']}",
        headers=auth,
    )
    assert queried.status_code == 200
    assert "event: job" not in queried.text
    assert "event: end" in queried.text


def test_event_stream_requires_auth_and_ownership(
    client, app, auth, upload
) -> None:
    job, _ = _terminal_job(client, auth, upload)
    missing = client.get(f"/api/v1/jobs/{job['id']}/events/stream")
    assert missing.status_code == 401

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.owner_id = "someone-else"
        session.commit()

    hidden = client.get(
        f"/api/v1/jobs/{job['id']}/events/stream", headers=auth
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "job_not_found"

    unknown = client.get(
        "/api/v1/jobs/not-a-job/events/stream", headers=auth
    )
    assert unknown.status_code == 404
