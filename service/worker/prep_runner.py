"""Prep subprocess command execution and process-group control."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping, Protocol


class PrepProcessHandle(Protocol):
    """Minimal process interface used by the prep worker loop."""

    pid: int

    def poll(self) -> int | None: ...

    def send_signal(self, signum: int) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def close(self) -> None: ...


class PrepSubprocessHandle:
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


class PrepSubprocessRunner:
    """Start the packmol-memgen command in a new process session."""

    def start(
        self,
        command: list[str],
        *,
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        env: Mapping[str, str] | None = None,
    ) -> PrepProcessHandle:
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
        return PrepSubprocessHandle(process, stdout_file, stderr_file)
