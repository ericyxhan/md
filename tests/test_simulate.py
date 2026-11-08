"""Planning and restart-order tests for simulate.py."""

from __future__ import annotations

import argparse
import signal
import tempfile
import unittest
from pathlib import Path

from config import ConfigError, load_config
from simulate import _restart_plan, _stage_sequence


def _write_config(directory: Path) -> Path:
    path = directory / "config.toml"
    path.write_text(
        """
[input]
complex = "input.pdb"

[minimization]
enabled = true

[[equilibration]]
name = "nvt"
steps = 10

[equilibration.integrator]
type = "langevin_middle"

[equilibration.barostat]
type = "none"

[[equilibration]]
name = "npt"
steps = 10

[equilibration.integrator]
type = "langevin_middle"

[equilibration.barostat]
type = "monte_carlo"

[production]
name = "production"
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
        encoding="utf-8",
    )
    return path


class PlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.config = load_config(_write_config(Path(self.temporary.name)))

    def test_stage_sequence_is_equilibration_then_production(self) -> None:
        sequence = _stage_sequence(self.config)
        self.assertEqual(
            [kind for kind, _ in sequence],
            ["equilibration", "equilibration", "production"],
        )
        self.assertEqual(
            [stage.name for _, stage in sequence],
            ["nvt", "npt", "production"],
        )

    def test_restart_all_includes_minimization(self) -> None:
        args = argparse.Namespace(restart=True, restart_stage=None)
        self.assertEqual(
            _restart_plan(self.config, args),
            {"minimization", "nvt", "npt", "production"},
        )

    def test_restart_stage_reruns_that_stage_and_later(self) -> None:
        args = argparse.Namespace(restart=False, restart_stage="npt")
        self.assertEqual(_restart_plan(self.config, args), {"npt", "production"})

    def test_restart_stage_validation(self) -> None:
        args = argparse.Namespace(restart=False, restart_stage="unknown")
        with self.assertRaises(ConfigError):
            _restart_plan(self.config, args)

    def test_no_restart_plan_is_empty(self) -> None:
        args = argparse.Namespace(restart=False, restart_stage=None)
        self.assertEqual(_restart_plan(self.config, args), set())


class SignalAndProgressTests(unittest.TestCase):
    def test_sigterm_handler_raises_keyboard_interrupt(self) -> None:
        from simulate import _install_signal_handlers

        previous = signal.getsignal(signal.SIGTERM)
        try:
            _install_signal_handlers()
            handler = signal.getsignal(signal.SIGTERM)
            with self.assertRaises(KeyboardInterrupt):
                handler(signal.SIGTERM, None)
        finally:
            signal.signal(signal.SIGTERM, previous)

    def test_progress_file_option_is_optional(self) -> None:
        from simulate import parse_args

        args = parse_args(["--config", "x.toml"])
        self.assertIsNone(args.progress_file)

        args = parse_args(["--progress-file", "p.json"])
        self.assertEqual(args.progress_file, Path("p.json"))

    def test_dry_run_does_not_write_progress(self) -> None:
        from simulate import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = _write_config(root)
            progress = root / "progress.json"
            previous = signal.getsignal(signal.SIGTERM)
            try:
                code = main(
                    [
                        "--config",
                        str(config),
                        "--dry-run",
                        "--progress-file",
                        str(progress),
                    ]
                )
            finally:
                signal.signal(signal.SIGTERM, previous)
            self.assertEqual(code, 0)
            self.assertFalse(progress.exists())


if __name__ == "__main__":
    unittest.main()
