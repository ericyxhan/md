"""Small fake API and process objects for worker-loop tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from client import WorkerAPIError


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeHandle:
    def __init__(
        self,
        *,
        exit_code: int | None = None,
        on_signal: Callable[["FakeHandle", int], None] | None = None,
        polls_before_exit: int = 0,
        on_poll: Callable[["FakeHandle", int], None] | None = None,
    ) -> None:
        self.pid = 4242
        self.returncode = exit_code
        self.signals: list[int] = []
        self.closed = False
        self.on_signal = on_signal
        self.polls_before_exit = polls_before_exit
        self.on_poll = on_poll
        self.polls = 0

    def poll(self) -> int | None:
        self.polls += 1
        if self.on_poll is not None:
            self.on_poll(self, self.polls)
        if self.returncode is None and self.polls > self.polls_before_exit:
            self.returncode = 0
        return self.returncode

    def send_signal(self, signum: int) -> None:
        self.signals.append(signum)
        if self.on_signal is not None:
            self.on_signal(self, signum)

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0

    def close(self) -> None:
        self.closed = True


class FakeRunner:
    def __init__(
        self,
        handle: FakeHandle | None = None,
        *,
        on_start: Callable[["FakeRunner"], None] | None = None,
    ) -> None:
        self.handle = handle or FakeHandle(exit_code=0)
        self.on_start = on_start
        self.command: list[str] | None = None
        self.cwd: Path | None = None
        self.stdout_path: Path | None = None
        self.stderr_path: Path | None = None
        self.starts = 0

    def start(
        self,
        command: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        env: Any = None,
    ) -> FakeHandle:
        self.starts += 1
        self.command = list(command)
        self.cwd = Path(cwd)
        self.stdout_path = Path(stdout_path)
        self.stderr_path = Path(stderr_path)
        self.stdout_path.parent.mkdir(parents=True, exist_ok=True)
        self.stdout_path.write_text("simulate stdout\n", encoding="utf-8")
        self.stderr_path.write_text("", encoding="utf-8")
        if self.on_start is not None:
            self.on_start(self)
        return self.handle


class FakeClient:
    def __init__(self, claims: list[dict[str, Any]] | None = None) -> None:
        self.claims = list(claims or [])
        self.claim_requests: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.progress_updates: list[tuple[str, dict[str, Any]]] = []
        self.stage_updates: list[tuple[str, dict[str, Any]]] = []
        self.finishes: list[tuple[str, dict[str, Any]]] = []
        self.cancel_requested = False
        self.progress_cancel_requested: bool | None = None
        self.stage_cancel_requested: bool | None = None
        self.progress_error: Exception | None = None
        self.stage_error: Exception | None = None
        self.finish_error: Exception | None = None

    def claim(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.claim_requests.append(payload)
        return self.claims.pop(0) if self.claims else None

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.heartbeats.append(payload)
        return {
            "cancel_requested": self.cancel_requested,
            "lease_expires_at": "2099-01-01T00:00:00Z",
        }

    def progress(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.progress_error is not None:
            raise self.progress_error
        self.progress_updates.append((job_id, payload))
        return {"cancel_requested": self._cancel("progress_cancel_requested")}

    def stage(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.stage_error is not None:
            raise self.stage_error
        self.stage_updates.append((job_id, payload))
        return {
            "ok": True,
            "cancel_requested": self._cancel("stage_cancel_requested"),
        }

    def _cancel(self, attribute: str) -> bool:
        override = getattr(self, attribute)
        return self.cancel_requested if override is None else override

    def finish(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.finish_error is not None:
            raise self.finish_error
        self.finishes.append((job_id, payload))
        return {"status": payload["status"]}


def write_progress(job_root: Path, **values: Any) -> None:
    path = job_root / "progress.json"
    path.write_text(json.dumps(values), encoding="utf-8")


def write_manifest(
    job_root: Path,
    stage: str,
    *,
    status: str = "completed",
    steps_completed: int = 0,
    attempt: int = 1,
    error: str | None = None,
) -> None:
    directory = job_root / "outputs" / "stages" / stage
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": stage,
        "status": status,
        "steps_completed": steps_completed,
        "attempt": attempt,
        "updated_at": "2026-11-07T12:00:00Z",
    }
    if error is not None:
        payload["error"] = error
    (directory / "stage.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def stale_error() -> WorkerAPIError:
    return WorkerAPIError(409, {"error": {"code": "stale_run_token"}})


def make_claim(
    tmp_path: Path,
    *,
    job_id: str = "job-1",
    stages: list[dict[str, Any]] | None = None,
    restart_mode: str = "resume",
    restart_stage: str | None = None,
) -> tuple[dict[str, Any], Any]:
    """Create a job workspace and return a claim payload plus config."""

    from config import WorkerConfig

    data_root = tmp_path / "data"
    job_root = data_root / "jobs" / job_id
    (job_root / "logs").mkdir(parents=True)
    (job_root / "config.toml").write_text("[run]\n", encoding="utf-8")
    config = WorkerConfig(
        api_url="http://api.test",
        token="worker-token",
        worker_id="gpu-0",
        hostname="test-host",
        data_root=data_root,
        gpu_uuid="GPU-TEST",
        simulate_path=tmp_path / "simulate.py",
        simulate_cwd=tmp_path,
        heartbeat_seconds=5.0,
        progress_poll_seconds=2.0,
        poll_seconds=1.0,
        cancel_grace_seconds=30.0,
        cancel_term_seconds=10.0,
    )
    claim = {
        "job_id": job_id,
        "run_token": "11111111-2222-4333-8444-555555555555",
        "job_root": str(job_root),
        "config_path": str(job_root / "config.toml"),
        "restart_mode": restart_mode,
        "restart_stage": restart_stage,
        "stages": stages
        or [
            {
                "name": "equil-01",
                "kind": "equilibration",
                "status": "pending",
                "steps_completed": 0,
                "steps_target": 10,
            }
        ],
    }
    return claim, config


def job_root_of(claim: dict[str, Any]) -> Path:
    return Path(claim["job_root"])

