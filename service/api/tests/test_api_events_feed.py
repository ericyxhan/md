"""Account-wide activity feed: shape, filtering, and back-paging."""

from __future__ import annotations

import pytest

from conftest import job_payload

PDB = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\n"
NEW_ACCOUNT = {
    "email": "ada@example.com",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "password": "correct horse battery",
}


def _create_job(client, auth, upload, name: str) -> str:
    file = upload("complex.pdb").json()
    response = client.post(
        "/api/v1/jobs",
        headers=auth,
        json=job_payload(file["id"], name=name),
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def _create_jobs(client, auth, upload, names: list[str]) -> list[str]:
    return [_create_job(client, auth, upload, name) for name in names]


def test_feed_returns_a_page_with_items_and_cursor(client, auth, upload) -> None:
    _create_jobs(client, auth, upload, ["job-a", "job-b"])

    response = client.get("/api/v1/jobs/events", headers=auth)
    assert response.status_code == 200
    payload = response.json()

    assert isinstance(payload["items"], list)
    assert "next_cursor" in payload
    # Two events per job (created, queued), newest first.
    assert [event["message"] for event in payload["items"]] == [
        "Job queued",
        "Job 'job-b' created",
        "Job queued",
        "Job 'job-a' created",
    ]


def test_feed_next_cursor_is_null_when_everything_fits(client, auth, upload) -> None:
    _create_job(client, auth, upload, "only-job")

    response = client.get("/api/v1/jobs/events?limit=50", headers=auth)
    assert response.status_code == 200
    assert response.json()["next_cursor"] is None


def test_feed_back_pages_through_the_whole_history(client, auth, upload) -> None:
    _create_jobs(client, auth, upload, ["job-a", "job-b", "job-c"])

    collected: list[tuple[str, int]] = []
    cursor = None
    pages = 0
    while True:
        query = "/api/v1/jobs/events?limit=2"
        if cursor:
            query += f"&cursor={cursor}"
        page = client.get(query, headers=auth).json()
        pages += 1
        assert page["items"], "an empty page must not be returned mid-walk"
        collected.extend((item["created_at"], item["id"]) for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert pages < 10, "pagination did not terminate"

    assert pages == 3  # six events, two per page
    assert len(collected) == len(set(collected)), "events were repeated across pages"
    # The whole history is in strict newest-first order.
    assert collected == sorted(collected, key=lambda item: (item[0], item[1]), reverse=True)


def test_feed_filters_by_job(client, auth, upload) -> None:
    first, second = _create_jobs(client, auth, upload, ["keep-me", "ignore-me"])

    response = client.get(f"/api/v1/jobs/events?job_id={first}", headers=auth)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert {event["job_id"] for event in items} == {first}
    assert second not in {event["job_id"] for event in items}


def test_feed_filters_by_event_type(client, auth, upload) -> None:
    _create_jobs(client, auth, upload, ["job-a", "job-b", "job-c"])

    response = client.get("/api/v1/jobs/events?event_type=created", headers=auth)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert {event["type"] for event in items} == {"created"}


def test_feed_filters_can_be_combined(client, auth, upload) -> None:
    first, second = _create_jobs(client, auth, upload, ["keep-me", "ignore-me"])

    response = client.get(
        f"/api/v1/jobs/events?job_id={first}&event_type=created", headers=auth
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [(event["job_id"], event["type"]) for event in items] == [(first, "created")]


def test_feed_rejects_a_job_the_caller_does_not_own(client, auth, upload) -> None:
    first = _create_job(client, auth, upload, "admin-job")

    # Registration signs the new account in, replacing the session cookie.
    registered = client.post("/api/v1/users", json=NEW_ACCOUNT)
    assert registered.status_code == 201

    # The job belongs to the administrator, so the filter target does not
    # exist as far as the new account is concerned: the same 404 every
    # other ownership check returns.  No bearer token here -- it would
    # authenticate as the administrator again.
    blocked = client.get(f"/api/v1/jobs/events?job_id={first}")
    assert blocked.status_code == 404
    assert blocked.json()["error"]["code"] == "job_not_found"


def test_feed_rejects_an_unknown_job_id(client, auth) -> None:
    response = client.get("/api/v1/jobs/events?job_id=no-such-job", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_feed_rejects_an_invalid_cursor(client, auth) -> None:
    response = client.get("/api/v1/jobs/events?cursor=not-a-cursor", headers=auth)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_feed_rejects_a_negative_limit(client, auth) -> None:
    response = client.get("/api/v1/jobs/events?limit=0", headers=auth)
    assert response.status_code == 422
