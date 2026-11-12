"""Artifact download and log tail/download tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.models import Artifact, Job
from app.settings import Settings
from conftest import job_payload

WORKER = {"worker_id": "gpu-0", "gpu_uuid": "GPU-1234"}


def _create_job(client, auth, upload, name: str = "artifacts") -> dict:
    file = upload("complex.pdb").json()
    payload = job_payload(file["id"])
    payload["name"] = name
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    return response.json()


def _claim(client, worker_auth, job_id: str) -> dict:
    response = client.post(
        "/internal/v1/jobs/claim", headers=worker_auth, json=WORKER
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job_id
    return body


def _finish(client, worker_auth, claimed: dict, artifacts: list[dict]) -> None:
    response = client.post(
        f"/internal/v1/jobs/{claimed['job_id']}/finish",
        headers=worker_auth,
        json={
            "run_token": claimed["run_token"],
            "status": "completed",
            "exit_code": 0,
            "artifacts": artifacts,
        },
    )
    assert response.status_code == 200, response.text


def _completed_job_with_artifacts(
    client, auth, worker_auth, settings: Settings, upload
) -> tuple[dict, dict[str, Path]]:
    job = _create_job(client, auth, upload)
    claimed = _claim(client, worker_auth, job["id"])
    root = settings.data_root / "jobs" / job["id"]

    trajectory = root / "outputs" / "stages" / "equil-01" / "trajectory.dcd"
    trajectory.parent.mkdir(parents=True, exist_ok=True)
    trajectory.write_bytes(b"DCD" * 100)

    worker_log = root / "logs" / "worker.log"
    worker_log.parent.mkdir(parents=True, exist_ok=True)
    worker_log.write_text("line one\nline two\nline three\n", encoding="utf-8")

    stage_json = root / "outputs" / "stages" / "equil-01" / "stage.json"
    stage_json.write_text('{"status": "completed"}\n', encoding="utf-8")

    _finish(
        client,
        worker_auth,
        claimed,
        [
            {
                "stage_name": "equil-01",
                "kind": "trajectory",
                "relative_path": "outputs/stages/equil-01/trajectory.dcd",
                "content_type": "application/octet-stream",
            },
            {
                "kind": "log",
                "relative_path": "logs/worker.log",
                "content_type": "text/plain",
            },
            {
                "stage_name": "equil-01",
                "kind": "metadata",
                "relative_path": "outputs/stages/equil-01/stage.json",
                "content_type": "application/json",
            },
        ],
    )
    return job, {
        "trajectory": trajectory,
        "worker_log": worker_log,
        "stage_json": stage_json,
    }


def test_list_filter_and_download_artifacts(
    client, auth, worker_auth, settings: Settings, upload
) -> None:
    job, paths = _completed_job_with_artifacts(
        client, auth, worker_auth, settings, upload
    )

    listing = client.get(f"/api/v1/jobs/{job['id']}/artifacts", headers=auth)
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert len(items) == 3
    by_path = {item["relative_path"]: item for item in items}
    trajectory = by_path["outputs/stages/equil-01/trajectory.dcd"]
    assert trajectory["kind"] == "trajectory"
    assert trajectory["stage_name"] == "equil-01"
    assert trajectory["size_bytes"] == paths["trajectory"].stat().st_size
    assert trajectory["content_type"] == "application/octet-stream"
    assert trajectory["name"] == "trajectory.dcd"

    logs = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts?kind=log", headers=auth
    ).json()["items"]
    assert [item["relative_path"] for item in logs] == ["logs/worker.log"]

    stage_items = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts?stage=equil-01", headers=auth
    ).json()["items"]
    assert {item["relative_path"] for item in stage_items} == {
        "outputs/stages/equil-01/stage.json",
        "outputs/stages/equil-01/trajectory.dcd",
    }

    invalid = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts?kind=banana", headers=auth
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_artifact_kind"

    download = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts/{trajectory['id']}",
        headers=auth,
    )
    assert download.status_code == 200, download.text
    assert download.content == b"DCD" * 100
    assert download.headers["content-type"] == "application/octet-stream"

    # The viewer asks for the headers before it loads a structure.
    head = client.head(
        f"/api/v1/jobs/{job['id']}/artifacts/{trajectory['id']}",
        headers=auth,
    )
    assert head.status_code == 200, head.text
    assert head.headers["content-type"] == "application/octet-stream"
    assert head.content == b""
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"

    unknown = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts/not-an-artifact",
        headers=auth,
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "artifact_not_found"


def test_artifacts_are_job_scoped_and_owner_scoped(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job, _ = _completed_job_with_artifacts(
        client, auth, worker_auth, settings, upload
    )
    other_job = _create_job(client, auth, upload, name="other")
    artifact_id = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts", headers=auth
    ).json()["items"][0]["id"]

    wrong_job = client.get(
        f"/api/v1/jobs/{other_job['id']}/artifacts/{artifact_id}",
        headers=auth,
    )
    assert wrong_job.status_code == 404
    assert wrong_job.json()["error"]["code"] == "artifact_not_found"

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.owner_id = "someone-else"
        session.commit()

    hidden = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts", headers=auth
    )
    assert hidden.status_code == 404

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.owner_id = "local"
        session.commit()


def test_artifact_download_rejects_symlinks_and_bad_rows(
    client, app, auth, worker_auth, settings: Settings, upload, tmp_path: Path
) -> None:
    job, paths = _completed_job_with_artifacts(
        client, auth, worker_auth, settings, upload
    )
    items = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts", headers=auth
    ).json()["items"]
    trajectory_id = next(
        item["id"]
        for item in items
        if item["relative_path"].endswith("trajectory.dcd")
    )

    # Replace a registered regular file with a symlink.
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    paths["trajectory"].unlink()
    paths["trajectory"].symlink_to(outside)

    symlink = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts/{trajectory_id}",
        headers=auth,
    )
    assert symlink.status_code == 404
    assert symlink.json()["error"]["code"] == "artifact_unavailable"

    # A corrupt database row must not escape the job root either.
    with app.state.session_factory() as session:
        record = Artifact(
            id="bad-artifact",
            job_id=job["id"],
            stage_name=None,
            kind="metadata",
            relative_path="../escape.txt",
            size_bytes=1,
            content_type="text/plain",
            created_at="2026-01-01T00:00:00Z",
        )
        session.add(record)
        session.commit()

    escaped = client.get(
        f"/api/v1/jobs/{job['id']}/artifacts/bad-artifact", headers=auth
    )
    assert escaped.status_code == 404
    assert escaped.json()["error"]["code"] == "artifact_unavailable"

    missing = client.get(f"/api/v1/jobs/{job['id']}/artifacts/{trajectory_id}", headers=auth)
    assert missing.status_code == 404


def test_log_list_tail_and_download(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job = _create_job(client, auth, upload)
    root = settings.data_root / "jobs" / job["id"]
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "worker.log").write_text(
        "\n".join(f"worker line {index}" for index in range(20)) + "\n",
        encoding="utf-8",
    )
    (logs / "simulate.stderr").write_text("stderr text\n", encoding="utf-8")
    # This file is not an allowlisted or registered log.
    (logs / "secret.txt").write_text("do not serve\n", encoding="utf-8")

    listing = client.get(f"/api/v1/jobs/{job['id']}/logs", headers=auth)
    assert listing.status_code == 200, listing.text
    names = {item["name"] for item in listing.json()["items"]}
    assert names == {"logs/worker.log", "logs/simulate.stderr"}
    assert all(item["size_bytes"] > 0 for item in listing.json()["items"])

    tail = client.get(
        f"/api/v1/jobs/{job['id']}/logs/logs/worker.log/tail?lines=3",
        headers=auth,
    )
    assert tail.status_code == 200, tail.text
    body = tail.json()
    assert body["name"] == "logs/worker.log"
    assert body["content"].splitlines() == [
        "worker line 17",
        "worker line 18",
        "worker line 19",
    ]
    assert body["lines"] == 3
    assert body["truncated"] is True

    by_basename = client.get(
        f"/api/v1/jobs/{job['id']}/logs/worker.log/tail?lines=1",
        headers=auth,
    )
    assert by_basename.status_code == 200
    assert by_basename.json()["content"].strip() == "worker line 19"

    download = client.get(
        f"/api/v1/jobs/{job['id']}/logs/logs/worker.log", headers=auth
    )
    assert download.status_code == 200
    assert download.text.startswith("worker line 0")
    assert "attachment" in download.headers["content-disposition"]

    missing = client.get(
        f"/api/v1/jobs/{job['id']}/logs/logs/secret.txt", headers=auth
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "log_not_found"

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        stored.owner_id = "someone-else"
        session.commit()
    hidden = client.get(f"/api/v1/jobs/{job['id']}/logs", headers=auth)
    assert hidden.status_code == 404


def test_registered_log_artifacts_are_listed(
    client, app, auth, worker_auth, settings: Settings, upload
) -> None:
    job, _ = _completed_job_with_artifacts(
        client, auth, worker_auth, settings, upload
    )
    root = settings.data_root / "jobs" / job["id"]
    extra = root / "outputs" / "logs" / "workflow.log"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("workflow log\n", encoding="utf-8")

    # Register the extra log through a second finish? Artifacts are only
    # registered by finish, so insert it the same way a retry would: directly
    # through the artifact service.
    from app.services.artifacts import register_artifacts
    from app.schemas_internal import ArtifactInput

    with app.state.session_factory() as session:
        stored = session.get(Job, job["id"])
        assert stored is not None
        register_artifacts(
            session,
            app.state.storage,
            stored,
            [
                ArtifactInput(
                    kind="log",
                    relative_path="outputs/logs/workflow.log",
                )
            ],
        )
        session.commit()

    entries = client.get(
        f"/api/v1/jobs/{job['id']}/logs", headers=auth
    ).json()["items"]
    assert "outputs/logs/workflow.log" in {item["name"] for item in entries}

    download = client.get(
        f"/api/v1/jobs/{job['id']}/logs/outputs/logs/workflow.log",
        headers=auth,
    )
    assert download.status_code == 200
    assert download.text == "workflow log\n"
