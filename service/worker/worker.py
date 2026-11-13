#!/usr/bin/env python3
"""Worker entry point: claim one job, run it, report progress and artifacts.

The worker never opens SQLite and never chooses an executable.  It claims a job
through the internal API, runs the fixed ``simulate.py`` command in a new
process session, polls the progress file and stage manifests, and reports every
state change through the API using the run token returned by ``claim``.

Cancellation escalates from SIGINT to SIGTERM to SIGKILL.  ``simulate.py``
preserves checkpoints on SIGINT, so a canceled job can be resumed later.
"""

from __future__ import annotations

import argparse
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from client import WorkerAPIError, WorkerClient
from config import (
    RESTART_MODES,
    ConfigError,
    WorkerConfig,
    load_config,
)
from progress import ProgressSnapshot, read_progress
from reconcile import (
    STAGE_NAME_RE,
    STAGE_STATUSES,
    StageManifest,
    read_stage_manifests,
    remove_stage_manifest,
    scan_artifacts,
    tail_text,
)
from runner import (
    ProcessHandle,
    SubprocessRunner,
    apply_restart_mode,
    build_command,
)
from views import generate_views

SLEEP_SLICE_SECONDS = 0.2
FINISH_ATTEMPTS = 3

_JOB_ID_RE = STAGE_NAME_RE
_TOKEN_RE = STAGE_NAME_RE
_OWNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _utcnow() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class ClaimError(ValueError):
    """The API returned a claim that is unsafe or malformed."""


class LostJob(RuntimeError):
    """The API rejected our run token; another worker owns the job."""


@dataclass(frozen=True)
class ClaimStage:
    name: str
    kind: str
    status: str
    steps_completed: int
    steps_target: int


@dataclass(frozen=True)
class ClaimedJob:
    job_id: str
    run_token: str
    job_root: Path
    config_path: Path
    restart_mode: str
    restart_stage: str | None
    stages: tuple[ClaimStage, ...]

    @property
    def stage_names(self) -> tuple[str, ...]:
        return tuple(stage.name for stage in self.stages)

    @property
    def stage_targets(self) -> dict[str, int]:
        return {stage.name: stage.steps_target for stage in self.stages}

    @property
    def stages_to_clear(self) -> tuple[str, ...]:
        """Stages whose stale manifests must be removed before launching.

        ``resume`` keeps every checkpoint and manifest.  ``restart`` and
        ``reparameterize`` invalidate all stage output, while ``restart_stage``
        invalidates the named stage and everything after it in the canonical
        execution order.
        """

        if self.restart_mode in ("restart", "reparameterize"):
            return self.stage_names
        if self.restart_mode != "restart_stage" or self.restart_stage is None:
            return ()
        names = self.stage_names
        try:
            index = names.index(self.restart_stage)
        except ValueError:
            return ()
        return names[index:]


def _string(data: dict[str, Any], key: str, *, maximum: int) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ClaimError(f"claim field {key!r} must be a string")
    value = value.strip()
    if not value or len(value) > maximum:
        raise ClaimError(f"claim field {key!r} has an invalid length")
    return value


def _integer(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ClaimError(f"claim field {key!r} must be an integer")
    if value < 0:
        raise ClaimError(f"claim field {key!r} must not be negative")
    return value


def parse_claim(data: dict[str, Any], config: WorkerConfig) -> ClaimedJob:
    """Validate a claim response before touching the filesystem.

    The API supplies absolute paths because the worker mounts the same data
    root, but an API bug or compromise must not be able to point the worker at
    an arbitrary directory.  The job root must be exactly
    ``DATA_ROOT/users/<owner_id>/jobs/<job_id>``.
    """

    job_id = _string(data, "job_id", maximum=64)
    if not _JOB_ID_RE.match(job_id):
        raise ClaimError("claim contains an invalid job id")

    owner_id = _string(data, "owner_id", maximum=64)
    if not _OWNER_ID_RE.match(owner_id):
        raise ClaimError("claim contains an invalid owner id")

    run_token = _string(data, "run_token", maximum=128)
    if not _TOKEN_RE.match(run_token):
        raise ClaimError("claim contains an invalid run token")

    raw_root = Path(_string(data, "job_root", maximum=4096))
    if not raw_root.is_absolute():
        raise ClaimError("claim job_root must be absolute")
    expected_root = config.job_root(owner_id, job_id).resolve()
    job_root = raw_root.resolve()
    if job_root != expected_root:
        raise ClaimError(
            "claim job_root is outside DATA_ROOT/users/<owner_id>/jobs/<job_id>"
        )
    if not job_root.is_dir():
        raise ClaimError("claim job_root does not exist")

    raw_config = Path(_string(data, "config_path", maximum=4096))
    if not raw_config.is_absolute():
        raise ClaimError("claim config_path must be absolute")
    config_path = raw_config.resolve()
    if config_path != job_root / "config.toml":
        raise ClaimError("claim config_path is not <job_root>/config.toml")
    if raw_config.is_symlink() or config_path.is_symlink():
        raise ClaimError("claim config_path must not be a symlink")
    if not config_path.is_file():
        raise ClaimError("claim config_path is missing")

    restart_mode = data.get("restart_mode") or "resume"
    if not isinstance(restart_mode, str) or restart_mode not in RESTART_MODES:
        raise ClaimError("claim contains an invalid restart mode")
    restart_stage = data.get("restart_stage")
    if restart_stage is not None and not isinstance(restart_stage, str):
        raise ClaimError("claim restart_stage must be a string or null")
    if restart_mode == "restart_stage":
        if not restart_stage or not STAGE_NAME_RE.match(restart_stage):
            raise ClaimError("restart_stage mode requires a valid stage name")
    else:
        restart_stage = None

    raw_stages = data.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ClaimError("claim must contain at least one stage")

    stages: list[ClaimStage] = []
    seen: set[str] = set()
    for item in raw_stages:
        if not isinstance(item, dict):
            raise ClaimError("claim stages must be objects")
        name = item.get("name")
        if not isinstance(name, str) or not STAGE_NAME_RE.match(name):
            raise ClaimError("claim contains an invalid stage name")
        if name in seen:
            raise ClaimError(f"claim contains duplicate stage {name!r}")
        seen.add(name)
        kind = item.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ClaimError(f"stage {name!r} has an invalid kind")
        status = item.get("status")
        if status not in STAGE_STATUSES:
            raise ClaimError(f"stage {name!r} has an invalid status")
        stages.append(
            ClaimStage(
                name=name,
                kind=kind[:24],
                status=status,
                steps_completed=_integer(item, "steps_completed"),
                steps_target=_integer(item, "steps_target"),
            )
        )

    if restart_stage is not None and restart_stage not in seen:
        raise ClaimError("restart_stage does not belong to the claimed job")

    return ClaimedJob(
        job_id=job_id,
        run_token=run_token,
        job_root=job_root,
        config_path=config_path,
        restart_mode=restart_mode,
        restart_stage=restart_stage,
        stages=tuple(stages),
    )


class Worker:
    """Single-job-at-a-time execution loop."""

    def __init__(
        self,
        config: WorkerConfig,
        client: Any,
        *,
        runner: Any | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.config = config
        self.client = client
        self.runner = runner or SubprocessRunner()
        self.clock = clock
        self.sleep = sleep
        self._stopping = False
        self._stage_signatures: dict[str, tuple[Any, ...]] = {}
        self._manifest_progress: dict[str, tuple[Any, ...]] = {}
        self._progress_key: tuple[Any, ...] | None = None
        self._next_progress_send = 0.0
        self._active_handle: ProcessHandle | None = None

    # -- Public control ---------------------------------------------------

    def request_stop(self) -> None:
        self._stopping = True

    def run(self, *, once: bool = False) -> None:
        self._log(
            f"worker {self.config.worker_id} version {self.config.version} "
            f"host={self.config.hostname} api={self.config.api_url}"
        )
        self._log_local_workspaces()
        next_heartbeat = 0.0
        try:
            while not self._stopping:
                now = self.clock()
                if now >= next_heartbeat:
                    self._heartbeat(None)
                    next_heartbeat = now + self.config.heartbeat_seconds
                claimed = self.run_once()
                if once:
                    break
                if not claimed:
                    self._sleep(self.config.poll_seconds)
        except KeyboardInterrupt:
            self._log("keyboard interrupt; stopping worker")
            self.request_stop()
        finally:
            self._heartbeat(None, status="offline")

    def run_once(self) -> bool:
        """Claim and execute at most one job.  Returns True when one ran."""

        try:
            data = self.client.claim(
                {
                    "worker_id": self.config.worker_id,
                    "gpu_uuid": self.config.gpu_uuid,
                }
            )
        except WorkerAPIError as exc:
            self._log(f"claim failed with API status {exc.status_code}: {exc.body}")
            return False
        except (httpx.HTTPError, OSError) as exc:
            self._log(f"claim failed: {exc}")
            return False

        if data is None:
            return False
        if not isinstance(data, dict):
            self._log("claim returned an unexpected payload")
            return False

        try:
            claim = parse_claim(data, self.config)
        except ClaimError as exc:
            self._log(f"rejected unsafe claim: {exc}")
            return False

        try:
            self._execute(claim)
        except Exception as exc:  # keep the worker alive and report the job
            self._log(f"worker error while running {claim.job_id}: {exc}")
            handle = getattr(self, "_active_handle", None)
            if handle is not None:
                try:
                    handle.send_signal(signal.SIGKILL)
                    handle.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                finally:
                    handle.close()
                self._active_handle = None
            self._finish_failure(
                claim,
                None,
                "worker_error",
                f"Worker error while running the job: {exc}",
            )
        return True

    # -- Job execution ----------------------------------------------------

    def _execute(self, claim: ClaimedJob) -> None:
        self._stage_signatures = {}
        self._manifest_progress = {}
        self._progress_key = None
        self._next_progress_send = 0.0

        logs = claim.job_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stdout_path = logs / "simulate.stdout"
        stderr_path = logs / "simulate.stderr"

        self._job_log(
            claim,
            f"claimed job {claim.job_id} in {claim.restart_mode!r} mode",
        )

        # A retry may leave a terminal progress document from the previous
        # attempt.  It is not a checkpoint, so remove it before launching;
        # simulate.py will write a fresh one.
        try:
            (claim.job_root / "progress.json").unlink(missing_ok=True)
        except OSError as exc:
            self._job_log(claim, f"could not clear the old progress file: {exc}")

        self._clear_restarted_manifests(claim)

        try:
            command = apply_restart_mode(
                build_command(
                    job_root=claim.job_root,
                    simulate_path=self.config.simulate_path,
                ),
                restart_mode=claim.restart_mode,
                restart_stage=claim.restart_stage,
            )
        except ValueError as exc:
            self._finish_failure(
                claim, None, "worker_start_failed", str(exc)
            )
            return

        self._job_log(claim, "starting simulation command")
        try:
            handle = self.runner.start(
                command,
                cwd=self.config.simulate_cwd,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                env=None,
            )
        except (OSError, ValueError) as exc:
            self._finish_failure(
                claim, None, "worker_start_failed", f"Could not start: {exc}"
            )
            return

        self._job_log(claim, f"simulation started as pid {handle.pid}")
        self._active_handle = handle
        next_heartbeat = self.clock()
        next_poll = self.clock()
        cancel_sent_at: float | None = None
        cancel_term_at: float | None = None
        cancel_killed = False
        lost = False
        exit_code: int | None = None

        while True:
            now = self.clock()

            if now >= next_heartbeat:
                response = self._heartbeat(claim)
                next_heartbeat = now + self.config.heartbeat_seconds
                if response and response.get("cancel_requested"):
                    if cancel_sent_at is None:
                        cancel_sent_at = self._begin_cancel(
                            claim, handle, "API cancellation request"
                        )

            if self._stopping and cancel_sent_at is None:
                cancel_sent_at = self._begin_cancel(
                    claim, handle, "worker is shutting down"
                )

            if now >= next_poll:
                next_poll = now + self.config.progress_poll_seconds
                outcome = self._poll_progress(claim, now)
                if outcome == "cancel" and cancel_sent_at is None:
                    cancel_sent_at = self._begin_cancel(
                        claim, handle, "API cancellation request"
                    )
                elif outcome == "lost":
                    lost = True
                    break

            if cancel_sent_at is not None and not cancel_killed:
                if (
                    cancel_term_at is None
                    and now - cancel_sent_at >= self.config.cancel_grace_seconds
                ):
                    handle.send_signal(signal.SIGTERM)
                    cancel_term_at = now
                    self._job_log(
                        claim,
                        "simulation did not stop after SIGINT; sent SIGTERM",
                    )
                elif (
                    cancel_term_at is not None
                    and now - cancel_term_at >= self.config.cancel_term_seconds
                ):
                    handle.send_signal(signal.SIGKILL)
                    cancel_killed = True
                    self._job_log(claim, "sent SIGKILL to the simulation")

            try:
                code = handle.poll()
            except OSError:
                code = -signal.SIGKILL
            if code is not None:
                exit_code = code
                break
            self._sleep(SLEEP_SLICE_SECONDS)

        if lost:
            self._job_log(
                claim,
                "run token is no longer valid; stopping the local process",
            )
            try:
                handle.send_signal(signal.SIGKILL)
                handle.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                handle.close()
                self._active_handle = None
            return

        self._job_log(
            claim,
            f"simulation exited with code {exit_code}",
        )
        self._finalize(
            claim,
            exit_code if exit_code is not None else -signal.SIGKILL,
            canceled=cancel_sent_at is not None,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        handle.close()
        self._active_handle = None

    def _clear_restarted_manifests(self, claim: ClaimedJob) -> None:
        """Remove manifests that a retry invalidated.

        A finished ``stage.json`` from a previous attempt would otherwise let
        ``simulate.py`` skip work (or let the worker report a false completion)
        after ``restart``, ``restart_stage``, or ``reparameterize``.
        """

        names = claim.stages_to_clear
        if not names:
            return
        cleared: list[str] = []
        for name in names:
            if remove_stage_manifest(claim.job_root, name):
                cleared.append(name)
        if cleared:
            self._job_log(
                claim,
                "cleared stale stage manifests: " + ", ".join(cleared),
            )

    def _poll_progress(self, claim: ClaimedJob, now: float) -> str | None:
        snapshot = read_progress(claim.job_root / "progress.json")
        if snapshot is not None:
            send = False
            if snapshot.change_key != self._progress_key:
                send = True
            elif now >= self._next_progress_send:
                send = True
            if send:
                self._next_progress_send = now + self.config.progress_send_seconds
                self._progress_key = snapshot.change_key
                try:
                    response = self.client.progress(
                        claim.job_id, snapshot.api_payload(claim.run_token)
                    )
                except WorkerAPIError as exc:
                    if exc.status_code == 409:
                        return "lost"
                    self._job_log(
                        claim,
                        f"progress update failed with API status "
                        f"{exc.status_code}: {exc.body}",
                    )
                except (httpx.HTTPError, OSError) as exc:
                    self._job_log(claim, f"progress update failed: {exc}")
                else:
                    if response.get("cancel_requested"):
                        return "cancel"

        try:
            manifests = read_stage_manifests(
                claim.job_root, claim.stage_names
            )
        except OSError as exc:
            self._job_log(claim, f"could not read stage manifests: {exc}")
            return None
        try:
            cancel = self._send_stage_updates(claim, manifests, force=False)
            cancel = (
                self._send_manifest_progress(claim, manifests, snapshot) or cancel
            )
        except LostJob:
            return "lost"
        return "cancel" if cancel else None

    def _send_manifest_progress(
        self,
        claim: ClaimedJob,
        manifests: dict[str, StageManifest],
        snapshot: ProgressSnapshot | None = None,
    ) -> bool:
        if snapshot is None:
            snapshot = read_progress(claim.job_root / "progress.json")
        if snapshot is not None and snapshot.api_phase is not None:
            return False
        targets = claim.stage_targets
        cancel_requested = False
        for name in claim.stage_names:
            manifest = manifests.get(name)
            if manifest is None:
                continue
            target = targets.get(name, 0)
            percent = (
                min(100.0, 100.0 * manifest.steps_completed / target)
                if target
                else 100.0
            )
            key = (name, manifest.status, manifest.steps_completed)
            if self._manifest_progress.get(name) == key:
                continue
            phase = "minimizing" if name == "minimization" else "simulating"
            payload = {
                "run_token": claim.run_token,
                "phase": phase,
                "stage": name,
                "step": manifest.steps_completed,
                "percent": percent,
            }
            if target:
                payload["total_steps"] = target
            try:
                response = self.client.progress(claim.job_id, payload)
            except WorkerAPIError as exc:
                if exc.status_code == 409:
                    raise LostJob from exc
                self._job_log(
                    claim,
                    f"manifest progress update failed with API status "
                    f"{exc.status_code}: {exc.body}",
                )
            except (httpx.HTTPError, OSError) as exc:
                self._job_log(
                    claim, f"manifest progress update failed: {exc}"
                )
            else:
                self._manifest_progress[name] = key
                if response.get("cancel_requested"):
                    cancel_requested = True
        return cancel_requested

    def _send_stage_updates(
        self,
        claim: ClaimedJob,
        manifests: dict[str, StageManifest],
        *,
        force: bool,
    ) -> bool:
        cancel_requested = False
        for name in claim.stage_names:
            manifest = manifests.get(name)
            if manifest is None:
                continue
            signature = manifest.signature
            if not force and self._stage_signatures.get(name) == signature:
                continue
            payload = {
                "run_token": claim.run_token,
                "name": name,
                "status": manifest.status,
                "steps_completed": manifest.steps_completed,
                "attempts": manifest.attempts,
                "manifest": manifest.data,
            }
            if manifest.error is not None:
                payload["error"] = manifest.error
            try:
                response = self.client.stage(claim.job_id, payload)
            except WorkerAPIError as exc:
                if exc.status_code == 409:
                    raise LostJob from exc
                self._job_log(
                    claim,
                    f"stage update for {name!r} failed with API status "
                    f"{exc.status_code}: {exc.body}",
                )
                continue
            except (httpx.HTTPError, OSError) as exc:
                self._job_log(
                    claim, f"stage update for {name!r} failed: {exc}"
                )
                continue
            self._stage_signatures[name] = signature
            if response.get("cancel_requested"):
                cancel_requested = True
        return cancel_requested

    # -- Finalization -----------------------------------------------------

    def _finalize(
        self,
        claim: ClaimedJob,
        exit_code: int,
        *,
        canceled: bool,
        stdout_path: Path,
        stderr_path: Path,
    ) -> None:
        manifests = read_stage_manifests(claim.job_root, claim.stage_names)
        try:
            self._send_stage_updates(claim, manifests, force=True)
        except LostJob:
            self._job_log(
                claim, "run token is no longer valid; skipping finish"
            )
            return

        snapshot = read_progress(claim.job_root / "progress.json")
        if snapshot is not None and snapshot.api_phase is not None:
            try:
                self.client.progress(
                    claim.job_id, snapshot.api_payload(claim.run_token)
                )
            except WorkerAPIError as exc:
                if exc.status_code == 409:
                    self._job_log(
                        claim, "run token is no longer valid; skipping finish"
                    )
                    return
            except (httpx.HTTPError, OSError):
                pass

        status, error_code, error_message = self._decide(
            claim,
            manifests,
            exit_code,
            canceled=canceled,
            stderr_path=stderr_path,
            stdout_path=stdout_path,
        )
        try:
            created_views = self._generate_views(claim)
            if created_views:
                self._job_log(
                    claim,
                    "generated views: "
                    + ", ".join(
                        view.relative_to(claim.job_root).as_posix()
                        for view in created_views
                    ),
                )
        except Exception as exc:  # views are cosmetic; never fail a job
            self._job_log(claim, f"view generation failed: {exc}")
        artifacts = scan_artifacts(
            claim.job_root,
            claim.stage_names,
            max_files=self.config.max_artifacts,
        )
        self._job_log(
            claim,
            f"reporting {status} with {len(artifacts)} artifacts",
        )
        payload: dict[str, Any] = {
            "run_token": claim.run_token,
            "status": status,
            "exit_code": exit_code,
            "artifacts": [
                {
                    "stage_name": item.stage_name,
                    "kind": item.kind,
                    "relative_path": item.relative_path,
                }
                for item in artifacts
            ],
        }
        if error_code is not None:
            payload["error_code"] = error_code
        if error_message is not None:
            payload["error_message"] = error_message[:8000]

        for attempt in range(1, FINISH_ATTEMPTS + 1):
            try:
                self.client.finish(claim.job_id, payload)
            except WorkerAPIError as exc:
                if exc.status_code == 409:
                    self._job_log(
                        claim, "run token is no longer valid; finish discarded"
                    )
                    return
                self._job_log(
                    claim,
                    f"finish failed with API status {exc.status_code}: "
                    f"{exc.body}",
                )
            except (httpx.HTTPError, OSError) as exc:
                self._job_log(claim, f"finish failed: {exc}")
            else:
                self._job_log(claim, f"finish accepted with status {status}")
                return
            if attempt < FINISH_ATTEMPTS:
                self._sleep(float(attempt))

    def _generate_views(self, claim: ClaimedJob) -> list[Path]:
        """Generate the browser views while renewing the job lease.

        The lease is only extended by heartbeats and progress posts.  A long
        view generation (a big system with several stages) would let the
        reaper expire the lease, mark the job ``worker_lost`` and discard a
        successful run, so the views are built on a worker thread and the
        lease is renewed until they are done.
        """

        created: list[Path] = []
        failure: BaseException | None = None

        def _run() -> None:
            nonlocal created, failure
            try:
                created = generate_views(claim.job_root)
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                failure = exc

        thread = threading.Thread(
            target=_run, name="view-generation", daemon=True
        )
        thread.start()
        interval = max(5.0, self.config.heartbeat_seconds)
        while thread.is_alive():
            thread.join(timeout=interval)
            if thread.is_alive():
                self._heartbeat(claim)

        if failure is not None:
            raise failure
        return created

    def _decide(
        self,
        claim: ClaimedJob,
        manifests: dict[str, StageManifest],
        exit_code: int,
        *,
        canceled: bool,
        stderr_path: Path,
        stdout_path: Path,
    ) -> tuple[str, str | None, str | None]:
        incomplete = [
            name
            for name in claim.stage_names
            if manifests.get(name) is None
            or manifests[name].status != "completed"
        ]

        if canceled:
            if exit_code == 0 and not incomplete:
                return "completed", None, None
            return "canceled", None, None

        if exit_code == 0:
            if not incomplete:
                return "completed", None, None
            detail = ", ".join(incomplete)
            return (
                "failed",
                "stage_incomplete",
                "simulate.py exited successfully but these stages are "
                f"missing or incomplete: {detail}",
            )

        tail = tail_text(stderr_path) or tail_text(stdout_path)
        message = f"simulate.py exited with code {exit_code}"
        if tail:
            message = f"{message}:\n{tail}"
        return "failed", "simulate_failed", message

    def _finish_failure(
        self,
        claim: ClaimedJob,
        exit_code: int | None,
        error_code: str,
        error_message: str,
    ) -> None:
        payload = {
            "run_token": claim.run_token,
            "status": "failed",
            "exit_code": exit_code,
            "error_code": error_code,
            "error_message": error_message[:8000],
            "artifacts": [],
        }
        self._job_log(claim, f"finishing failed: {error_message}")
        try:
            self.client.finish(claim.job_id, payload)
        except (WorkerAPIError, httpx.HTTPError, OSError) as exc:
            self._job_log(claim, f"could not report failure: {exc}")

    # -- Cancellation -----------------------------------------------------

    def _begin_cancel(
        self, claim: ClaimedJob, handle: ProcessHandle, reason: str
    ) -> float:
        self._job_log(claim, f"canceling: {reason}; sending SIGINT")
        try:
            handle.send_signal(signal.SIGINT)
        except OSError as exc:
            self._job_log(claim, f"could not send SIGINT: {exc}")
        return self.clock()

    # -- API helpers ------------------------------------------------------

    def _heartbeat(
        self, claim: ClaimedJob | None, *, status: str = "online"
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "worker_id": self.config.worker_id,
            "hostname": self.config.hostname,
            "gpu_name": self.config.gpu_name,
            "gpu_uuid": self.config.gpu_uuid,
            "version": self.config.version,
            "status": status,
        }
        if claim is not None and status == "online":
            payload["current_job_id"] = claim.job_id
            payload["run_token"] = claim.run_token
        try:
            response = self.client.heartbeat(payload)
        except WorkerAPIError as exc:
            self._log(f"heartbeat failed with API status {exc.status_code}")
            return None
        except (httpx.HTTPError, OSError) as exc:
            self._log(f"heartbeat failed: {exc}")
            return None
        return response if isinstance(response, dict) else None

    # -- Logging and small helpers ---------------------------------------

    def _log(self, message: str) -> None:
        print(f"[{_utcnow()}] {message}", flush=True)

    def _job_log(self, claim: ClaimedJob, message: str) -> None:
        self._log(f"job {claim.job_id}: {message}")
        path = claim.job_root / "logs" / "worker.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{_utcnow()}] {message}\n")
        except OSError as exc:
            self._log(f"could not write job log: {exc}")

    def _log_local_workspaces(self) -> None:
        # Workspaces live at DATA_ROOT/users/<owner_id>/jobs/<job_id>.
        users_root = self.config.jobs_root
        if not users_root.is_dir():
            return
        found = 0
        try:
            owner_dirs = sorted(users_root.iterdir())
        except OSError:
            return
        for owner_dir in owner_dirs:
            if not owner_dir.is_dir() or owner_dir.name.startswith("."):
                continue
            jobs_dir = owner_dir / "jobs"
            if not jobs_dir.is_dir():
                continue
            try:
                entries = sorted(jobs_dir.iterdir())
            except OSError:
                continue
            for entry in entries:
                if found >= 20:
                    break
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if (entry / "progress.json").is_file():
                    found += 1
                    self._log(
                        f"local workspace {entry.name} exists but is not "
                        "claimed automatically; the API is authoritative"
                    )

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleep(seconds)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MD service worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and run at most one job, then exit.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Seconds between idle claim attempts.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=None,
        help="Seconds between worker heartbeats.",
    )
    parser.add_argument(
        "--progress-poll-seconds",
        type=float,
        default=None,
        help="Seconds between progress-file and stage-manifest polls.",
    )
    parser.add_argument(
        "--cancel-grace-seconds",
        type=float,
        default=None,
        help="Seconds to wait after SIGINT before SIGTERM.",
    )
    parser.add_argument(
        "--cancel-term-seconds",
        type=float,
        default=None,
        help="Seconds to wait after SIGTERM before SIGKILL.",
    )
    return parser.parse_args(argv)


def _apply_overrides(config: WorkerConfig, args: argparse.Namespace) -> WorkerConfig:
    overrides: dict[str, float] = {}
    for name in (
        "poll_seconds",
        "heartbeat_seconds",
        "progress_poll_seconds",
        "cancel_grace_seconds",
        "cancel_term_seconds",
    ):
        value = getattr(args, name)
        if value is not None:
            if value < 0:
                raise ConfigError(f"--{name.replace('_', '-')} must be non-negative")
            overrides[name] = value
    return replace(config, **overrides)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = _apply_overrides(load_config(), args)
    except ConfigError as exc:
        print(f"Worker configuration error: {exc}", file=sys.stderr)
        return 2

    client = WorkerClient(
        config.api_url,
        config.token,
        timeout=config.request_timeout_seconds,
    )
    worker = Worker(config, client)

    def _stop(signum, _frame) -> None:
        print(
            f"[{_utcnow()}] received signal {signum}; stopping after the "
            "current job is reported",
            flush=True,
        )
        worker.request_stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    try:
        worker.run(once=args.once)
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
