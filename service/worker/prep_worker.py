#!/usr/bin/env python3
"""Prep worker: claim membrane-embedding jobs, run Packmol-Memgen, report progress.

The prep worker never opens SQLite and never chooses an executable.  It claims a
prep job through the internal API, runs packmol-memgen in a new process session,
reports progress, and reports completion or failure through the API using the
run token returned by claim.

Cancellation escalates from SIGINT to SIGTERM to SIGKILL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from prep_config import (
    PrepConfig,
    PrepConfigError,
    load_config,
)
from prep_client import PrepAPIError, PrepClient
from prep_ops import (
    add_ligand,
    inspect_pdb,
    keep_selection,
    remove_ligand,
    remove_residues,
    select_chain,
)
from prep_runner import PrepProcessHandle, PrepSubprocessRunner

SLEEP_SLICE_SECONDS = 0.2
FINISH_ATTEMPTS = 3

# Packmol restarts its GENCAN counter at zero for every structure block, so
# the log is the only reliable progress signal.  Note that packmol rewrites its
# solution file after *every* loop, which means the presence of the output
# file says nothing about how far the packing has actually progressed.
_PACKMOL_LOOP_RE = re.compile(r"^\s*Starting GENCAN loop:\s*(\d+)\s*$", re.M)
_PACKMOL_TYPE_RE = re.compile(r"^\s*Packing molecules of type:\s*(\d+)\s*$", re.M)
# The account id is part of the workspace path, so it has to be a plain
# identifier and nothing else.
_OWNER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# The packmol input file never changes while a job runs, and the log only
# grows.  Both are parsed on every progress poll, so the results are cached
# instead of re-reading the same bytes a couple of times a second.
_BLOCK_BUDGET_CACHE: dict[str, tuple[tuple[int, int], list[tuple[str, int, int]]]] = {}
_LOG_STATE_CACHE: dict[str, tuple[int, int, int, str]] = {}


def _packmol_block_budget(inp_path: Path) -> list[tuple[str, int, int]]:
    """Return ``(structure_name, loop_budget, molecule_count)`` per block.

    The top-level ``nloop`` applies to any structure that does not declare
    its own.  The loop budget is an upper bound: packmol stops a block early
    once the configured tolerance is met.
    """

    try:
        stat = inp_path.stat()
    except OSError:
        return []
    key = str(inp_path)
    signature = (stat.st_size, stat.st_mtime_ns)
    cached = _BLOCK_BUDGET_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1]

    try:
        text = inp_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    default_nloop = 20
    blocks: list[tuple[str, int, int]] = []
    current_name: str | None = None
    current_nloop = default_nloop
    current_count = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("structure "):
            current_name = line.split(None, 1)[1].strip()
            current_nloop = default_nloop
            current_count = 0
            continue
        if line == "end structure":
            if current_name is not None:
                blocks.append((current_name, current_nloop, current_count))
            current_name = None
            current_nloop = default_nloop
            current_count = 0
            continue
        if line.startswith("nloop "):
            try:
                value = int(line.split(None, 1)[1])
            except ValueError:
                continue
            if current_name is not None:
                current_nloop = value
            else:
                default_nloop = value
        elif line.startswith("number ") and current_name is not None:
            try:
                current_count += int(line.split(None, 1)[1])
            except ValueError:
                pass

    _BLOCK_BUDGET_CACHE[key] = (signature, blocks)
    return blocks


def _packmol_log_state(log_path: Path) -> tuple[int, int]:
    """Return ``(blocks_started, current_loop)`` for the packmol log.

    Only the bytes appended since the last call are parsed; the log grows
    while packmol runs and the progress poll happens every couple of
    seconds.  A line that was only partly written is carried over to the
    next call.
    """

    key = str(log_path)
    offset, blocks_started, current_loop, pending = _LOG_STATE_CACHE.get(
        key, (0, 0, 0, "")
    )
    try:
        size = log_path.stat().st_size
        if size < offset:
            # The log was truncated or replaced; start over.
            offset, blocks_started, current_loop, pending = 0, 0, 0, ""
        if size == offset:
            return blocks_started, current_loop
        with log_path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
    except OSError:
        return blocks_started, current_loop

    text = pending + chunk.decode("utf-8", errors="replace")
    if text.endswith("\n"):
        pending = ""
        lines = text.split("\n")[:-1]
    else:
        # The last line is only partly written; carry it over to the next
        # call so a marker split across two reads is still matched.
        head, _, tail = text.rpartition("\n")
        pending = tail
        lines = head.split("\n") if head else []

    for line in lines:
        type_match = _PACKMOL_TYPE_RE.match(line)
        if type_match:
            blocks_started += 1
            current_loop = 0
            continue
        loop_match = _PACKMOL_LOOP_RE.match(line)
        if loop_match:
            current_loop = int(loop_match.group(1))

    _LOG_STATE_CACHE[key] = (
        offset + len(chunk),
        blocks_started,
        current_loop,
        pending,
    )
    return blocks_started, current_loop


def _packmol_progress(work_dir: Path) -> tuple[float, str]:
    """Estimate packmol's completion from its log and input file.

    Progress is measured in *molecules placed* rather than optimization
    loops: packmol stops a block as soon as its tolerance is met, so the
    remaining blocks usually converge in a couple of loops no matter how many
    loops their budget allows.  Molecule count is both monotonic and a
    meaningful sense of how much work is left.

    Returns ``(percent, message)``.
    """

    log_path = work_dir / "packmol.log"
    inp_path = work_dir / "packmol.inp"

    if not log_path.is_file():
        return 0.0, "packmol-memgen starting"

    # Walk the log once.  Packmol prints "Packing molecules of type: N"
    # before each structure block and then counts GENCAN loops inside that
    # block.  The type header is a reliable block marker; the GENCAN counter
    # alone is not, because a block may finish after a single loop and the
    # counter then never leaves zero.
    blocks_started, current_loop = _packmol_log_state(log_path)

    budget = _packmol_block_budget(inp_path)
    if not budget:
        return 1.0, "packmol-memgen packing"

    total_blocks = len(budget)
    # The last block that started is the one currently being packed.
    done_blocks = min(max(0, blocks_started - 1), total_blocks)
    index = min(done_blocks, total_blocks - 1)

    total_molecules = sum(count for _name, _loops, count in budget)
    done_molecules = sum(count for _name, _loops, count in budget[:done_blocks])

    current_name, current_budget, current_count = budget[index]

    if total_molecules > 0:
        placed = done_molecules
        if blocks_started < total_blocks and current_count > 0 and current_budget > 0:
            # Assume the block is roughly proportional to its loop progress.
            fraction = min(1.0, current_loop / max(current_budget, 1))
            placed += int(current_count * fraction)
        molecule_share = placed / total_molecules
    else:
        molecule_share = 0.0

    # Blend the two signals.  Molecule count alone barely moves while the
    # protein and lipid blocks are packed (one protein molecule out of 80k),
    # which reads as "stuck"; block count alone ignores that the water
    # blocks dominate the work.  The message carries the precise detail.
    block_share = done_blocks / total_blocks if total_blocks else 0.0
    percent = min(
        99.0, max(1.0, 100.0 * (0.5 * block_share + 0.5 * molecule_share))
    )

    message = (
        f"packing {current_name} "
        f"(block {done_blocks + 1}/{total_blocks}, loop {current_loop}"
        f"/{current_budget})"
    )
    return percent, message


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
class ClaimedPrepJob:
    prep_job_id: str
    run_token: str
    # Membrane-embed fields (set for type == "membrane_embed")
    protein_file_id: str | None = None
    lipid: str | None = None
    box_padding_nm: float | None = None
    orientation: str | None = None
    ionic_strength_molar: float | None = None
    # System-prep fields (set for type == "system_prep")
    job_type: str | None = None
    steps: list[dict[str, Any]] | None = None
    source_path: Path | None = None
    work_dir: Path | None = None

    @property
    def output_pdb(self) -> Path:
        assert self.work_dir is not None
        return self.work_dir / "embedded.pdb"

    @property
    def system_output_pdb(self) -> Path:
        assert self.work_dir is not None
        return self.work_dir / "system_prep.pdb"


class PrepWorker:
    """Single-prep-job-at-a-time execution loop."""

    def __init__(
        self,
        config: PrepConfig,
        client: Any,
        *,
        runner: Any | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        self.config = config
        self.client = client
        self.runner = runner or PrepSubprocessRunner()
        self.clock = clock
        self.sleep = sleep
        self._stopping = False
        self._active_handle: PrepProcessHandle | None = None
        self._progress_key: tuple[Any, ...] | None = None
        self._next_progress_send = 0.0

    # -- Public control ---------------------------------------------------

    def request_stop(self) -> None:
        self._stopping = True

    def run(self, *, once: bool = False) -> None:
        self._log(
            f"prep worker {self.config.worker_id} version {self.config.version} "
            f"host={self.config.hostname} api={self.config.api_url}"
        )
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
        """Claim and execute at most one prep job.  Returns True when one ran."""

        try:
            data = self.client.claim_prep(
                {
                    "worker_id": self.config.worker_id,
                }
            )
        except PrepAPIError as exc:
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
            claim = self._parse_claim(data)
        except ClaimError as exc:
            self._log(f"rejected unsafe claim: {exc}")
            return False

        try:
            self._execute(claim)
        except Exception as exc:  # keep the worker alive and report the job
            self._log(f"worker error while running {claim.prep_job_id}: {exc}")
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
                "prep_worker_error",
                f"Worker error while running prep job: {exc}",
            )
        return True

    # -- Job execution ----------------------------------------------------

    def _execute(self, claim: ClaimedPrepJob) -> None:
        assert claim.work_dir is not None
        claim.work_dir.mkdir(parents=True, exist_ok=True)

        if claim.job_type == "system_prep":
            self._execute_system_prep(claim)
            return

        # membrane_embed (default)
        assert claim.source_path is not None
        self._job_log(
            claim,
            f"claimed prep job {claim.prep_job_id} for lipid {claim.lipid}",
        )

        # Copy the input structure into the work directory so that packmol-memgen
        # can write intermediate files next to it without needing write access
        # to the API's uploads directory.
        local_pdb = claim.work_dir / "input.pdb"
        shutil.copy2(claim.source_path, local_pdb)

        # Locate the PACKMOL binary (pip-installed packmol provides it on PATH).
        packmol_bin = shutil.which("packmol")
        packmol_args = []
        if packmol_bin:
            packmol_args = ["--packmol", packmol_bin]

        # Build the packmol-memgen command
        cmd = [
            self.config.packmol_path,
            "--pdb", str(local_pdb),
            "--lipids", str(claim.lipid),
            "--output", str(claim.output_pdb),
            "--dist", str(int(claim.box_padding_nm * 10)),  # nm -> Angstroms
            "--salt",
            "--saltcon", str(claim.ionic_strength_molar),
            "--notprotonate",
            "--keep",
        ] + packmol_args
        if claim.orientation:
            cmd.append("--preoriented")

        self._job_log(claim, "starting packmol-memgen command")
        try:
            handle = self.runner.start(
                command=cmd,
                cwd=claim.work_dir,
                stdout_path=claim.work_dir / "logs" / "packmol-memgen.stdout",
                stderr_path=claim.work_dir / "logs" / "packmol-memgen.stderr",
                env=None,
            )
        except (OSError, ValueError) as exc:
            self._finish_failure(
                claim, None, "prep_start_failed", f"Could not start: {exc}"
            )
            return

        self._job_log(claim, f"packmol-memgen started as pid {handle.pid}")
        self._active_handle = handle
        next_heartbeat = self.clock()
        next_progress = self.clock()
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

            if now >= next_progress:
                next_progress = now + self.config.progress_poll_seconds
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
                        "packmol-memgen did not stop after SIGINT; sent SIGTERM",
                    )
                elif (
                    cancel_term_at is not None
                    and now - cancel_term_at >= self.config.cancel_term_seconds
                ):
                    handle.send_signal(signal.SIGKILL)
                    cancel_killed = True
                    self._job_log(claim, "sent SIGKILL to packmol-memgen")

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
            f"packmol-memgen exited with code {exit_code}",
        )
        self._finalize(
            claim,
            exit_code if exit_code is not None else -signal.SIGKILL,
            canceled=cancel_sent_at is not None,
        )
        handle.close()
        self._active_handle = None

    # -- System prep execution ---------------------------------------------

    def _execute_system_prep(self, claim: ClaimedPrepJob) -> None:
        """Run system preparation operations directly (no subprocess)."""

        assert claim.source_path is not None
        assert claim.work_dir is not None
        assert claim.steps is not None

        self._job_log(
            claim,
            f"claimed system prep job {claim.prep_job_id} "
            f"with {len(claim.steps)} step(s)",
        )

        current_pdb = claim.source_path
        output_pdb = claim.system_output_pdb

        try:
            for step_index, step in enumerate(claim.steps):
                operation = step["operation"]
                step_log = f"step {step_index + 1}/{len(claim.steps)}: {operation}"
                self._job_log(claim, f"running {step_log}")

                if operation == "remove_ligand":
                    ligand = step.get("ligand_to_remove")
                    if not ligand:
                        raise ValueError(
                            f"step {step_index + 1}: remove_ligand requires ligand_to_remove"
                        )
                    intermediate = claim.work_dir / f"step_{step_index + 1}.pdb"
                    remove_ligand(current_pdb, ligand, intermediate)
                    self._job_log(
                        claim,
                        f"  removed ligand {ligand!r} -> {intermediate.name}",
                    )

                elif operation == "select_chain":
                    chain = step.get("chain_to_keep")
                    if not chain:
                        raise ValueError(
                            f"step {step_index + 1}: select_chain requires chain_to_keep"
                        )
                    intermediate = claim.work_dir / f"step_{step_index + 1}.pdb"
                    select_chain(current_pdb, [chain], intermediate)
                    self._job_log(
                        claim,
                        f"  kept chain {chain!r} -> {intermediate.name}",
                    )

                elif operation == "remove_residues":
                    specs = step.get("residue_specs")
                    if not specs:
                        raise ValueError(
                            f"step {step_index + 1}: remove_residues requires residue_specs"
                        )
                    intermediate = claim.work_dir / f"step_{step_index + 1}.pdb"
                    remove_residues(current_pdb, specs, intermediate)
                    self._job_log(
                        claim,
                        f"  removed {len(specs)} residue(s) -> {intermediate.name}",
                    )

                elif operation == "keep_selection":
                    specs = step.get("residue_specs")
                    if not specs:
                        raise ValueError(
                            f"step {step_index + 1}: keep_selection requires residue_specs"
                        )
                    intermediate = claim.work_dir / f"step_{step_index + 1}.pdb"
                    keep_selection(current_pdb, specs, intermediate)
                    self._job_log(
                        claim,
                        f"  kept {len(specs)} residue(s) -> {intermediate.name}",
                    )

                elif operation == "add_ligand":
                    ligand_ids = step.get("ligand_file_ids", [])
                    if not ligand_ids:
                        raise ValueError(
                            f"step {step_index + 1}: add_ligand requires ligand_file_ids"
                        )
                    # Resolve ligand paths from the claim data.
                    ligand_paths = []
                    ligand_path_map = step.get("_ligand_paths", {})
                    for lig_id in ligand_ids:
                        lig_path_raw = ligand_path_map.get(lig_id)
                        if lig_path_raw:
                            ligand_paths.append(Path(lig_path_raw))
                        else:
                            raise ValueError(
                                f"step {step_index + 1}: no path for ligand {lig_id}"
                            )
                    intermediate = claim.work_dir / f"step_{step_index + 1}.pdb"
                    add_ligand(current_pdb, ligand_paths, intermediate)
                    self._job_log(
                        claim,
                        f"  added {len(ligand_paths)} ligand(s) -> {intermediate.name}",
                    )
                else:
                    raise ValueError(f"step {step_index + 1}: unknown operation {operation!r}")

                current_pdb = intermediate

            # Final output
            import shutil as _shutil
            _shutil.copy2(current_pdb, output_pdb)

            self._job_log(
                claim,
                f"system prep complete: {output_pdb.name}",
            )

            # Report completion through finish with the output path.
            self._finalize_system_prep(claim, output_pdb)

        except Exception as exc:
            self._job_log(claim, f"system prep failed: {exc}")
            self._finish_failure(
                claim, None, "prep_failed", f"System prep failed: {exc}"
            )

    def _finalize_system_prep(self, claim: ClaimedPrepJob, output_pdb: Path) -> None:
        """Report system prep completion with the output PDB path."""

        import json as _json

        payload: dict[str, Any] = {
            "run_token": claim.run_token,
            "status": "completed",
            "output_file_ids": [str(output_pdb)],
        }

        self._job_log(
            claim,
            f"reporting completed with output {output_pdb.name}",
        )

        for attempt in range(1, FINISH_ATTEMPTS + 1):
            try:
                self.client.finish(claim.prep_job_id, payload)
            except PrepAPIError as exc:
                if exc.status_code == 409:
                    self._job_log(
                        claim, "run token is no longer valid; finish discarded"
                    )
                    return
                self._job_log(
                    claim,
                    f"finish failed with API status {exc.status_code}: {exc.body}",
                )
            except (httpx.HTTPError, OSError) as exc:
                self._job_log(claim, f"finish failed: {exc}")
            else:
                self._job_log(claim, f"finish accepted with status completed")
                return
            if attempt < FINISH_ATTEMPTS:
                self._sleep(float(attempt))

    def _poll_progress(
        self, claim: ClaimedPrepJob, now: float
    ) -> str | None:
        """Report packmol's real packing progress.

        The output file is rewritten by packmol after every GENCAN loop, so
        its presence cannot be used as a progress signal — doing so reported
        "100% / finalizing" while the packing was still running.  The packmol
        log is parsed instead.
        """

        work_dir = claim.work_dir
        if work_dir is None:
            percent, message = 1.0, "packmol-memgen running"
        else:
            percent, message = _packmol_progress(work_dir)

        # Nothing changed since the last report: do not spend a database
        # write on it.  The prep heartbeat still surfaces cancel requests,
        # so this does not delay a cancellation.
        key = (percent, message)
        if key == self._progress_key and now < self._next_progress_send:
            return None
        self._progress_key = key
        self._next_progress_send = now + self.config.progress_send_seconds

        try:
            response = self.client.progress(
                claim.prep_job_id,
                {
                    "run_token": claim.run_token,
                    "phase": "packing",
                    "percent": percent,
                    "message": message,
                },
            )
        except PrepAPIError as exc:
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

        return None

    def _finalize(
        self,
        claim: ClaimedPrepJob,
        exit_code: int,
        *,
        canceled: bool,
    ) -> None:
        status: str
        error_code: str | None = None
        error_message: str | None = None

        if canceled:
            status = "canceled"
        elif exit_code == 0 and claim.output_pdb.is_file():
            status = "completed"
        else:
            status = "failed"
            error_code = "prep_failed"
            error_message = (
                f"packmol-memgen exited with code {exit_code}"
            )

        output_file_ids: list[str] = []
        if status == "completed":
            # The prep worker cannot register files directly; the API will
            # register them based on the output paths reported here.
            output_file_ids = [str(claim.output_pdb)]

            # Packing is done; tell the UI it is finalizing the outputs
            # before the finish call lands.
            try:
                self.client.progress(
                    claim.prep_job_id,
                    {
                        "run_token": claim.run_token,
                        "phase": "finalizing",
                        "percent": 99.0,
                        "message": "embedding complete, writing outputs",
                    },
                )
            except (PrepAPIError, httpx.HTTPError, OSError):
                pass

        payload: dict[str, Any] = {
            "run_token": claim.run_token,
            "status": status,
            "output_file_ids": output_file_ids,
        }
        if error_code is not None:
            payload["error_code"] = error_code
        if error_message is not None:
            payload["error_message"] = error_message[:8000]

        self._job_log(
            claim,
            f"reporting {status} with exit code {exit_code}",
        )

        for attempt in range(1, FINISH_ATTEMPTS + 1):
            try:
                self.client.finish(claim.prep_job_id, payload)
            except PrepAPIError as exc:
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

    def _finish_failure(
        self,
        claim: ClaimedPrepJob,
        exit_code: int | None,
        error_code: str,
        error_message: str,
    ) -> None:
        payload = {
            "run_token": claim.run_token,
            "status": "failed",
            "output_file_ids": [],
            "error_code": error_code,
            "error_message": error_message[:8000],
        }
        self._job_log(claim, f"finishing failed: {error_message}")
        try:
            self.client.finish(claim.prep_job_id, payload)
        except (PrepAPIError, httpx.HTTPError, OSError) as exc:
            self._job_log(claim, f"could not report failure: {exc}")

    # -- Cancellation -----------------------------------------------------

    def _begin_cancel(
        self, claim: ClaimedPrepJob, handle: PrepProcessHandle, reason: str
    ) -> float:
        self._job_log(claim, f"canceling: {reason}; sending SIGINT")
        try:
            handle.send_signal(signal.SIGINT)
        except OSError as exc:
            self._job_log(claim, f"could not send SIGINT: {exc}")
        return self.clock()

    # -- API helpers ------------------------------------------------------

    def _heartbeat(
        self, claim: ClaimedPrepJob | None, *, status: str = "online"
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "worker_id": self.config.worker_id,
            "hostname": self.config.hostname,
            "version": self.config.version,
            "status": status,
        }
        if claim is not None and status == "online":
            payload["current_job_id"] = claim.prep_job_id
            payload["run_token"] = claim.run_token
        try:
            response = self.client.heartbeat(payload)
        except PrepAPIError as exc:
            self._log(f"heartbeat failed with API status {exc.status_code}")
            return None
        except (httpx.HTTPError, OSError) as exc:
            self._log(f"heartbeat failed: {exc}")
            return None
        return response if isinstance(response, dict) else None

    def _parse_claim(self, data: dict[str, Any]) -> ClaimedPrepJob:
        """Validate a claim response before touching the filesystem."""

        prep_job_id = str(data.get("prep_job_id", ""))
        if not prep_job_id:
            raise ClaimError("claim missing prep_job_id")

        owner_id = str(data.get("owner_id", ""))
        if not owner_id:
            raise ClaimError("claim missing owner_id")
        if not _OWNER_ID_RE.match(owner_id):
            raise ClaimError("claim contains an invalid owner id")

        run_token = str(data.get("run_token", ""))
        if not run_token:
            raise ClaimError("claim missing run_token")

        job_type = str(data.get("job_type", ""))

        source_path_raw = data.get("source_path")
        source_path: Path | None = None
        if source_path_raw is not None:
            source_path = Path(str(source_path_raw))
            if not source_path.is_absolute():
                raise ClaimError("claim source_path must be absolute")
            if not source_path.is_file():
                raise ClaimError("claim source_path is missing")

        work_dir_raw = data.get("work_dir")
        work_dir: Path | None = None
        if work_dir_raw is not None:
            work_dir = Path(str(work_dir_raw))
            if not work_dir.is_absolute():
                raise ClaimError("claim work_dir must be absolute")
            # The API supplies absolute paths because the worker mounts the
            # same data root, but an API bug or compromise must not be able
            # to point the worker at an arbitrary directory.  The workspace
            # must be exactly DATA_ROOT/users/<owner_id>/prep/<prep_job_id>.
            expected = self.config.prep_root(owner_id, prep_job_id)
            if work_dir.resolve() != expected.resolve():
                raise ClaimError(
                    "claim work_dir is outside "
                    "DATA_ROOT/users/<owner_id>/prep/<prep_job_id>"
                )

        if job_type == "system_prep":
            steps = data.get("steps")
            if not isinstance(steps, list) or not steps:
                raise ClaimError("system_prep claim missing steps")
            return ClaimedPrepJob(
                prep_job_id=prep_job_id,
                run_token=run_token,
                job_type=job_type,
                steps=steps,
                source_path=source_path,
                work_dir=work_dir,
            )

        # membrane_embed (default)
        protein_file_id = str(data.get("protein_file_id", ""))
        if not protein_file_id:
            raise ClaimError("claim missing protein_file_id")

        lipid = str(data.get("lipid", ""))
        if not lipid:
            raise ClaimError("claim missing lipid")

        if source_path is None:
            raise ClaimError("claim missing source_path")
        if work_dir is None:
            raise ClaimError("claim missing work_dir")

        return ClaimedPrepJob(
            prep_job_id=prep_job_id,
            run_token=run_token,
            job_type=job_type or "membrane_embed",
            protein_file_id=protein_file_id,
            lipid=lipid,
            box_padding_nm=float(data.get("box_padding_nm", 1.5)),
            orientation=data.get("orientation"),
            ionic_strength_molar=float(data.get("ionic_strength_molar", 0.15)),
            source_path=source_path,
            work_dir=work_dir,
        )

    # -- Logging and small helpers ---------------------------------------

    def _log(self, message: str) -> None:
        print(f"[{_utcnow()}] {message}", flush=True)

    def _job_log(self, claim: ClaimedPrepJob, message: str) -> None:
        self._log(f"prep job {claim.prep_job_id}: {message}")
        log_path = claim.work_dir / "logs" / "prep-worker.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{_utcnow()}] {message}\n")
        except OSError as exc:
            self._log(f"could not write prep job log: {exc}")

    def _sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleep(seconds)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MD service prep worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and run at most one prep job, then exit.",
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
        help="Seconds between progress polls.",
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


def _apply_overrides(config: PrepConfig, args: argparse.Namespace) -> PrepConfig:
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
                raise PrepConfigError(f"--{name.replace('_', '-')} must be non-negative")
            overrides[name] = value
    return replace(config, **overrides)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = _apply_overrides(load_config(), args)
    except PrepConfigError as exc:
        print(f"Prep worker configuration error: {exc}", file=sys.stderr)
        return 2

    client = PrepClient(
        config.api_url,
        config.token,
        timeout=config.request_timeout_seconds,
    )
    worker = PrepWorker(config, client)

    def _stop(signum, _frame) -> None:
        print(
            f"[{_utcnow()}] received signal {signum}; stopping after the "
            "current prep job is reported",
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
