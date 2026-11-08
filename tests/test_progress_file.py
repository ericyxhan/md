"""Tests for the live progress file and workflow terminal states."""

from __future__ import annotations

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from config import load_config
from run_progress import ProgressWriter
from simulate import run_workflow


def _write_config(directory: Path) -> Path:
    path = directory / "config.toml"
    path.write_text(
        """
[input]
complex = "input.pdb"

[minimization]
enabled = false

[[equilibration]]
name = "nvt"
steps = 10

[equilibration.integrator]
type = "langevin_middle"

[equilibration.barostat]
type = "none"
""",
        encoding="utf-8",
    )
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ProgressWriterTests(unittest.TestCase):
    def test_writes_an_atomic_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            writer = ProgressWriter(path)
            writer.write(
                phase="simulating",
                status="running",
                stage="equil-01",
                step=25,
                total_steps=100,
                percent=25.0,
            )

            data = _read(path)
            self.assertEqual(data["phase"], "simulating")
            self.assertEqual(data["stage"], "equil-01")
            self.assertEqual(data["step"], 25)
            self.assertEqual(data["percent"], 25.0)
            self.assertIn("updated_at", data)
            self.assertFalse((path.parent / "progress.json.tmp").exists())

            writer.update(step=50)
            data = _read(path)
            self.assertEqual(data["step"], 50)
            self.assertEqual(data["phase"], "simulating")

    def test_percent_is_finite_and_clamped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            writer = ProgressWriter(path)
            writer.write(phase="simulating", percent=150)
            self.assertEqual(_read(path)["percent"], 100.0)
            writer.write(phase="simulating", percent=-5)
            self.assertEqual(_read(path)["percent"], 0.0)
            writer.write(phase="simulating", percent=float("nan"))
            self.assertIsNone(_read(path)["percent"])

    def test_disabled_writer_does_nothing(self) -> None:
        writer = ProgressWriter(None)
        self.assertFalse(writer.enabled)
        writer.write(phase="starting")
        writer.update(step=1)

    def test_write_failure_warns_and_disables(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            blocker = Path(temporary) / "not-a-directory"
            blocker.write_text("", encoding="utf-8")
            writer = ProgressWriter(blocker / "progress.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                writer.write(phase="starting")
            self.assertIn("could not write progress file", stderr.getvalue())
            self.assertFalse(writer.enabled)
            writer.update(step=1)


class WorkflowTerminalStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = load_config(_write_config(self.root))
        self.progress = self.root / "progress.json"
        self.args = argparse.Namespace(
            progress_file=self.progress,
            restart=False,
            restart_stage=None,
            reparameterize=False,
        )

    def test_success_ends_completed(self) -> None:
        with mock.patch("simulate._run_workflow"):
            run_workflow(self.config, self.args)
        self.assertEqual(_read(self.progress)["phase"], "completed")

    def test_keyboard_interrupt_ends_canceled(self) -> None:
        with mock.patch(
            "simulate._run_workflow", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                run_workflow(self.config, self.args)
        data = _read(self.progress)
        self.assertEqual(data["phase"], "canceled")
        self.assertEqual(data["status"], "canceled")

    def test_error_ends_failed(self) -> None:
        with mock.patch(
            "simulate._run_workflow", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                run_workflow(self.config, self.args)
        data = _read(self.progress)
        self.assertEqual(data["phase"], "failed")
        self.assertEqual(data["status"], "failed")
        self.assertIn("boom", data["error"])

    def test_disabled_progress_file_writes_nothing(self) -> None:
        args = argparse.Namespace(progress_file=None)
        with mock.patch("simulate._run_workflow"):
            run_workflow(self.config, args)

    def test_workflow_emits_lifecycle_phases(self) -> None:
        from simulate import _run_workflow

        class RecordingProgress:
            def __init__(self) -> None:
                self.events: list[dict] = []

            def write(self, **fields) -> None:
                self.events.append(dict(fields))

            def update(self, **fields) -> None:
                self.events.append(dict(fields))

        progress = RecordingProgress()
        platform = mock.Mock()
        platform.getName.return_value = "CPU"
        prepared = mock.Mock()
        prepared.topology.getNumAtoms.return_value = 4
        system = mock.Mock()
        system.getNumParticles.return_value = 4

        with (
            mock.patch("simulate._get_platform", return_value=platform),
            mock.patch(
                "simulate.resolve_inputs",
                return_value=mock.Mock(describe=lambda: "input"),
            ),
            mock.patch("simulate.ensure_parameterized", return_value=mock.Mock()),
            mock.patch(
                "simulate._load_prepared_system",
                return_value=(prepared, system),
            ),
            mock.patch("simulate._ensure_minimization", return_value=None),
            mock.patch("simulate._run_stages", return_value=None),
        ):
            _run_workflow(self.config, self.args, progress)

        phases = [
            event["phase"]
            for event in progress.events
            if event.get("phase") is not None
        ]
        self.assertEqual(phases[0], "starting")
        self.assertIn("parameterizing", phases)
        self.assertIn("simulating", phases)


if __name__ == "__main__":
    unittest.main()
