"""End-to-end worker loop tests with a fake API and fake runner."""

from __future__ import annotations

import signal
from dataclasses import replace
from pathlib import Path

from fakes import (
    FakeClient,
    FakeClock,
    FakeHandle,
    FakeRunner,
    job_root_of,
    make_claim,
    stale_error,
    write_manifest,
    write_progress,
)
from worker import Worker


def _run_worker(claim, config, client, runner) -> Worker:
    clock = FakeClock()
    worker = Worker(
        config,
        client,
        runner=runner,
        clock=clock,
        sleep=clock.sleep,
    )
    assert worker.run_once() is True
    return worker


def test_successful_job_reports_progress_stages_and_artifacts(
    tmp_path: Path,
) -> None:
    stages = [
        {
            "name": "minimization",
            "kind": "minimization",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 0,
        },
        {
            "name": "equil-01",
            "kind": "equilibration",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 10,
        },
    ]
    claim, config = make_claim(tmp_path, stages=stages)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        write_manifest(root, "minimization", steps_completed=0)
        write_manifest(root, "equil-01", steps_completed=10)
        stage = root / "outputs" / "stages" / "equil-01"
        (stage / "checkpoint.chk").write_text("checkpoint", encoding="utf-8")
        (stage / "trajectory.dcd").write_text("trajectory", encoding="utf-8")
        (stage / "state.xml").write_text("<state/>", encoding="utf-8")
        outside = tmp_path / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        (root / "outputs" / "escape.txt").symlink_to(outside)

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0), on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert runner.starts == 1
    assert runner.command is not None
    assert runner.command[1] == str(config.simulate_path)
    assert "--progress-file" in runner.command
    assert runner.cwd == config.simulate_cwd

    assert len(client.finishes) == 1
    job_id, payload = client.finishes[0]
    assert job_id == claim["job_id"]
    assert payload["status"] == "completed"
    assert payload["exit_code"] == 0
    paths = {item["relative_path"] for item in payload["artifacts"]}
    artifacts = {
        item["relative_path"]: item for item in payload["artifacts"]
    }
    assert "config.toml" in paths
    assert "logs/worker.log" in paths
    assert "outputs/stages/equil-01/checkpoint.chk" in paths
    assert "outputs/escape.txt" not in paths
    assert artifacts["outputs/stages/equil-01/checkpoint.chk"]["kind"] == (
        "checkpoint"
    )
    assert artifacts["outputs/stages/equil-01/trajectory.dcd"]["kind"] == (
        "trajectory"
    )
    assert artifacts["outputs/stages/equil-01/state.xml"]["kind"] == "state"
    assert artifacts["outputs/stages/equil-01/stage.json"]["stage_name"] == (
        "equil-01"
    )

    stage_names = {payload["name"] for _, payload in client.stage_updates}
    assert stage_names == {"minimization", "equil-01"}
    assert all(
        payload["status"] == "completed"
        for _, payload in client.stage_updates
    )

    progress = [payload for _, payload in client.progress_updates]
    assert any(item.get("phase") == "minimizing" for item in progress)
    assert any(item.get("phase") == "simulating" for item in progress)

    log_text = (root / "logs" / "worker.log").read_text(encoding="utf-8")
    assert "simulation exited with code 0" in log_text
    assert "finish accepted" in log_text


def test_progress_changes_and_stage_transitions_are_reported(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(tmp_path)
    config = replace(config, progress_poll_seconds=0.1)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        write_manifest(root, "equil-01", status="running", steps_completed=0)

    def on_poll(handle: FakeHandle, count: int) -> None:
        if count >= 3:
            write_manifest(root, "equil-01", steps_completed=10)
        else:
            write_manifest(
                root,
                "equil-01",
                status="running",
                steps_completed=count * 2,
            )
        write_progress(
            root,
            phase="simulating",
            status="running",
            stage="equil-01",
            step=count * 2,
            total_steps=10,
        )

    client = FakeClient([claim])
    runner = FakeRunner(
        FakeHandle(
            exit_code=None,
            polls_before_exit=2,
            on_poll=on_poll,
        ),
        on_start=on_start,
    )
    _run_worker(claim, config, client, runner)

    steps = [
        payload.get("step")
        for _, payload in client.progress_updates
        if payload.get("stage") == "equil-01"
    ]
    assert 2 in steps
    assert 4 in steps
    assert client.finishes[0][1]["status"] == "completed"

    statuses = [
        payload["status"]
        for _, payload in client.stage_updates
        if payload["name"] == "equil-01"
    ]
    assert "running" in statuses
    assert statuses[-1] == "completed"


def test_failure_reports_stderr_and_exit_code(tmp_path: Path) -> None:
    claim, config = make_claim(tmp_path)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        assert runner.stderr_path is not None
        runner.stderr_path.write_text(
            "Error: equilibration diverged\n", encoding="utf-8"
        )
        write_progress(
            root,
            phase="failed",
            status="failed",
            stage="equil-01",
            error="diverged",
        )

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=1), on_start=on_start)
    _run_worker(claim, config, client, runner)

    _, payload = client.finishes[0]
    assert payload["status"] == "failed"
    assert payload["exit_code"] == 1
    assert payload["error_code"] == "simulate_failed"
    assert "equilibration diverged" in payload["error_message"]
    assert "code 1" in payload["error_message"]


def test_exit_zero_with_missing_stage_manifest_is_a_failure(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(tmp_path)
    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0))
    _run_worker(claim, config, client, runner)

    _, payload = client.finishes[0]
    assert payload["status"] == "failed"
    assert payload["error_code"] == "stage_incomplete"
    assert "equil-01" in payload["error_message"]


def test_cancel_requests_sigint_and_preserves_checkpoints(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(tmp_path)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        stage = root / "outputs" / "stages" / "equil-01"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "checkpoint.chk").write_text(
            "preserved", encoding="utf-8"
        )

    def on_signal(handle: FakeHandle, signum: int) -> None:
        if signum == signal.SIGINT:
            write_manifest(root, "equil-01", status="canceled")
            handle.returncode = 130

    client = FakeClient([claim])
    client.cancel_requested = True
    handle = FakeHandle(exit_code=None, on_signal=on_signal)
    runner = FakeRunner(handle, on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert handle.signals == [signal.SIGINT]
    _, payload = client.finishes[0]
    assert payload["status"] == "canceled"
    assert payload["exit_code"] == 130
    paths = {item["relative_path"] for item in payload["artifacts"]}
    assert "outputs/stages/equil-01/checkpoint.chk" in paths
    assert (
        root / "outputs" / "stages" / "equil-01" / "checkpoint.chk"
    ).read_text(encoding="utf-8") == "preserved"


def test_cancel_escalates_to_sigterm(tmp_path: Path) -> None:
    claim, config = make_claim(tmp_path)
    config = replace(
        config,
        cancel_grace_seconds=0.2,
        cancel_term_seconds=0.1,
    )

    def on_signal(handle: FakeHandle, signum: int) -> None:
        if signum == signal.SIGTERM:
            write_manifest(Path(claim["job_root"]), "equil-01", status="canceled")
            handle.returncode = 143

    client = FakeClient([claim])
    client.cancel_requested = True
    handle = FakeHandle(exit_code=None, on_signal=on_signal, polls_before_exit=100)
    runner = FakeRunner(handle)
    _run_worker(claim, config, client, runner)

    assert handle.signals == [signal.SIGINT, signal.SIGTERM]
    _, payload = client.finishes[0]
    assert payload["status"] == "canceled"
    assert payload["exit_code"] == 143


def test_worker_shutdown_cancels_the_running_job(tmp_path: Path) -> None:
    claim, config = make_claim(tmp_path)
    root = job_root_of(claim)

    def on_signal(handle: FakeHandle, signum: int) -> None:
        if signum == signal.SIGINT:
            write_manifest(root, "equil-01", status="canceled")
            handle.returncode = 130

    client = FakeClient([claim])
    handle = FakeHandle(exit_code=None, on_signal=on_signal)
    runner = FakeRunner(handle)

    clock = FakeClock()
    worker = Worker(
        config, client, runner=runner, clock=clock, sleep=clock.sleep
    )

    def request_stop(runner: FakeRunner) -> None:
        worker.request_stop()

    runner.on_start = request_stop
    assert worker.run_once() is True
    assert handle.signals == [signal.SIGINT]
    assert client.finishes[0][1]["status"] == "canceled"


def test_stale_run_token_stops_the_process_without_finishing(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(tmp_path)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        write_progress(
            root,
            phase="simulating",
            stage="equil-01",
            step=1,
            total_steps=10,
        )

    client = FakeClient([claim])
    client.progress_error = stale_error()
    handle = FakeHandle(exit_code=None, polls_before_exit=100)
    runner = FakeRunner(handle, on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert client.finishes == []
    assert signal.SIGKILL in handle.signals
    assert handle.closed is True


def test_unsafe_job_root_is_rejected_without_starting(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "config.toml").write_text("", encoding="utf-8")
    claim["job_root"] = str(outside)
    claim["config_path"] = str(outside / "config.toml")

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0))
    clock = FakeClock()
    worker = Worker(
        config, client, runner=runner, clock=clock, sleep=clock.sleep
    )

    assert worker.run_once() is False
    assert runner.starts == 0
    assert client.finishes == []


def test_empty_queue_does_nothing(tmp_path: Path) -> None:
    _claim, config = make_claim(tmp_path)
    client = FakeClient()
    runner = FakeRunner(FakeHandle(exit_code=0))
    clock = FakeClock()
    worker = Worker(
        config, client, runner=runner, clock=clock, sleep=clock.sleep
    )

    assert worker.run_once() is False
    assert runner.starts == 0


def test_restart_mode_is_passed_to_the_fixed_command(
    tmp_path: Path,
) -> None:
    claim, config = make_claim(
        tmp_path,
        restart_mode="restart_stage",
        restart_stage="equil-01",
    )
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        write_manifest(root, "equil-01", steps_completed=10)

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0), on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert runner.command is not None
    assert runner.command[-2:] == ["--restart-stage", "equil-01"]


def _four_stages() -> list[dict]:
    return [
        {
            "name": "minimization",
            "kind": "minimization",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 0,
        },
        {
            "name": "equil-01",
            "kind": "equilibration",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 10,
        },
        {
            "name": "equil-02",
            "kind": "equilibration",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 10,
        },
        {
            "name": "production",
            "kind": "production",
            "status": "pending",
            "steps_completed": 0,
            "steps_target": 20,
        },
    ]


def _existing_manifests(root: Path) -> list[str]:
    stages_dir = root / "outputs" / "stages"
    if not stages_dir.is_dir():
        return []
    return sorted(
        path.parent.name
        for path in stages_dir.glob("*/stage.json")
        if path.is_file()
    )


def test_restart_clears_every_stale_stage_manifest(tmp_path: Path) -> None:
    stages = _four_stages()
    claim, config = make_claim(
        tmp_path, stages=stages, restart_mode="restart"
    )
    root = job_root_of(claim)
    for stage in stages:
        write_manifest(
            root, stage["name"], steps_completed=stage["steps_target"]
        )
    assert _existing_manifests(root) == [
        "equil-01",
        "equil-02",
        "minimization",
        "production",
    ]

    seen: dict[str, list[str]] = {}

    def on_start(runner: FakeRunner) -> None:
        seen["manifests"] = _existing_manifests(root)

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0), on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert seen["manifests"] == []
    _, payload = client.finishes[0]
    assert payload["status"] == "failed"
    assert payload["error_code"] == "stage_incomplete"
    assert "production" in payload["error_message"]


def test_restart_stage_clears_only_the_target_and_later(tmp_path: Path) -> None:
    stages = _four_stages()
    claim, config = make_claim(
        tmp_path,
        stages=stages,
        restart_mode="restart_stage",
        restart_stage="equil-01",
    )
    root = job_root_of(claim)
    for stage in stages:
        write_manifest(
            root, stage["name"], steps_completed=stage["steps_target"]
        )

    seen: dict[str, list[str]] = {}

    def on_start(runner: FakeRunner) -> None:
        seen["manifests"] = _existing_manifests(root)
        write_manifest(root, "minimization", steps_completed=0)
        write_manifest(root, "equil-01", steps_completed=10)

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0), on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert seen["manifests"] == ["minimization"]
    _, payload = client.finishes[0]
    assert payload["status"] == "failed"
    assert payload["error_code"] == "stage_incomplete"
    assert "equil-02" in payload["error_message"]
    assert "production" in payload["error_message"]


def test_resume_keeps_existing_stage_manifests(tmp_path: Path) -> None:
    claim, config = make_claim(tmp_path, restart_mode="resume")
    root = job_root_of(claim)
    write_manifest(root, "equil-01", steps_completed=10)

    seen: dict[str, list[str]] = {}

    def on_start(runner: FakeRunner) -> None:
        seen["manifests"] = _existing_manifests(root)

    client = FakeClient([claim])
    runner = FakeRunner(FakeHandle(exit_code=0), on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert seen["manifests"] == ["equil-01"]
    assert client.finishes[0][1]["status"] == "completed"


def test_progress_response_can_request_cancellation(tmp_path: Path) -> None:
    claim, config = make_claim(tmp_path)
    root = job_root_of(claim)

    def on_start(runner: FakeRunner) -> None:
        write_progress(
            root,
            phase="simulating",
            status="running",
            stage="equil-01",
            step=1,
            total_steps=10,
        )

    def on_signal(handle: FakeHandle, signum: int) -> None:
        if signum == signal.SIGINT:
            write_manifest(root, "equil-01", status="canceled")
            handle.returncode = 130

    client = FakeClient([claim])
    client.cancel_requested = False
    client.progress_cancel_requested = True
    handle = FakeHandle(exit_code=None, on_signal=on_signal)
    runner = FakeRunner(handle, on_start=on_start)
    _run_worker(claim, config, client, runner)

    assert handle.signals == [signal.SIGINT]
    assert client.finishes[0][1]["status"] == "canceled"
