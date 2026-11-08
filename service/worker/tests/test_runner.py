"""Fixed command construction and real subprocess capture tests."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

import pytest

from runner import (
    SubprocessRunner,
    apply_restart_mode,
    build_command,
)


def test_build_command_is_fixed(tmp_path: Path) -> None:
    command = build_command(
        job_root=tmp_path,
        python="/usr/bin/python3",
        simulate_path=Path("/app/simulate.py"),
    )
    assert command == [
        "/usr/bin/python3",
        "/app/simulate.py",
        "--config",
        str(tmp_path / "config.toml"),
        "--progress-file",
        str(tmp_path / "progress.json"),
    ]


def test_restart_modes_append_exactly_one_flag(tmp_path: Path) -> None:
    command = build_command(job_root=tmp_path)
    assert apply_restart_mode(
        command, restart_mode="resume", restart_stage=None
    ) == command
    assert apply_restart_mode(
        command, restart_mode="restart", restart_stage=None
    )[-1] == "--restart"
    assert apply_restart_mode(
        command, restart_mode="reparameterize", restart_stage=None
    )[-1] == "--reparameterize"
    assert apply_restart_mode(
        command, restart_mode="restart_stage", restart_stage="equil-02"
    )[-2:] == ["--restart-stage", "equil-02"]


def test_restart_mode_validation(tmp_path: Path) -> None:
    command = build_command(job_root=tmp_path)
    with pytest.raises(ValueError):
        apply_restart_mode(
            command, restart_mode="shell", restart_stage=None
        )
    with pytest.raises(ValueError):
        apply_restart_mode(
            command, restart_mode="restart_stage", restart_stage="../escape"
        )
    with pytest.raises(ValueError):
        apply_restart_mode(
            command, restart_mode="restart_stage", restart_stage=None
        )


def test_subprocess_runner_captures_output(tmp_path: Path) -> None:
    runner = SubprocessRunner()
    stdout_path = tmp_path / "logs" / "simulate.stdout"
    stderr_path = tmp_path / "logs" / "simulate.stderr"
    handle = runner.start(
        [
            sys.executable,
            "-c",
            "import sys; print('hello'); print('oops', file=sys.stderr)",
        ],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        env=None,
    )
    try:
        assert handle.wait(timeout=10) == 0
        assert handle.poll() == 0
    finally:
        handle.close()
    assert stdout_path.read_text(encoding="utf-8").strip() == "hello"
    assert stderr_path.read_text(encoding="utf-8").strip() == "oops"


def test_subprocess_runner_starts_a_new_process_group(tmp_path: Path) -> None:
    runner = SubprocessRunner()
    stdout_path = tmp_path / "out.log"
    stderr_path = tmp_path / "err.log"
    handle = runner.start(
        [sys.executable, "-c", "import os; print(os.getpgrp(), os.getpid())"],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        env=None,
    )
    try:
        assert handle.wait(timeout=10) == 0
    finally:
        handle.close()
    group, pid = stdout_path.read_text(encoding="utf-8").split()
    assert int(group) == int(pid)


def test_sigint_terminates_process_group(tmp_path: Path) -> None:
    runner = SubprocessRunner()
    stdout_path = tmp_path / "out.log"
    stderr_path = tmp_path / "err.log"
    handle = runner.start(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        env=None,
    )
    try:
        handle.send_signal(signal.SIGINT)
        returncode = handle.wait(timeout=10)
        assert returncode != 0
    finally:
        handle.close()
