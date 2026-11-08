"""Fixed subprocess command construction and process-group control.

The worker never accepts an executable, script path, or arbitrary flags from a
user or from the API.  Only the restart mode, which is validated by the API,
selects one optional flag.  The child is started in a new session so a
cancellation can signal the whole process group, including the parameterizer
child started by ``simulate.py``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Protocol

from config import RESTART_MODES

STAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def build_command(
    *,
    job_root: Path,
    python: str | None = None,
    simulate_path: Path = Path("/app/simulate.py"),
) -> list[str]:
    return [
        python or sys.executable,
        str(simulate_path),
        "--config",
        str(job_root / "config.toml"),
        "--progress-file",
        str(job_root / "progress.json"),
    ]


def apply_restart_mode(
    command: list[str],
    *,
    restart_mode: str | None,
    restart_stage: str | None,
) -> list[str]:
    mode = restart_mode or "resume"
    if mode not in RESTART_MODES:
        raise ValueError(f"Unsupported restart mode: {mode!r}")
    if mode == "resume":
        return command
    if mode == "restart":
        return [*command, "--restart"]
    if mode == "reparameterize":
        return [*command, "--reparameterize"]
    if not restart_stage or not STAGE_NAME_RE.match(restart_stage):
        raise ValueError("restart_stage requires a valid stage name")
    return [*command, "--restart-stage", restart_stage]


class ProcessHandle(Protocol):
    """Minimal process interface used by the worker loop and fake runners."""

    pid: int

    def poll(self) -> int | None: ...

    def send_signal(self, signum: int) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def close(self) -> None: ...


class SubprocessHandle:
    """One child process plus its captured stdout/stderr file objects."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        stdout_file,
        stderr_file,
    ) -> None:
        self._process = process
        self._stdout_file = stdout_file
        self._stderr_file = stderr_file

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> int | None:
        return self._process.poll()

    def send_signal(self, signum: int) -> None:
        try:
            os.killpg(os.getpgid(self._process.pid), signum)
        except (ProcessLookupError, PermissionError):
            return
        except OSError:
            try:
                self._process.send_signal(signum)
            except (ProcessLookupError, OSError):
                return

    def wait(self, timeout: float | None = None) -> int:
        return self._process.wait(timeout=timeout)

    def close(self) -> None:
        for handle in (self._stdout_file, self._stderr_file):
            try:
                handle.close()
            except OSError:
                pass


class SubprocessRunner:
    """Start the fixed simulation command in a new process session."""

    def __init__(self, python: str | None = None) -> None:
        self.python = python

    def start(
        self,
        command: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle:
        stdout_path = Path(stdout_path)
        stderr_path = Path(stderr_path)
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        environment = dict(os.environ if env is None else env)
        environment.setdefault("PYTHONUNBUFFERED", "1")

        stdout_file = stdout_path.open("ab", buffering=0)
        stderr_file = stderr_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                env=environment,
                start_new_session=True,
            )
        except BaseException:
            stdout_file.close()
            stderr_file.close()
            raise
        return SubprocessHandle(process, stdout_file, stderr_file)
