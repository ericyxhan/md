"""Planning and restart-order tests for simulate.py."""

from __future__ import annotations

import argparse
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


if __name__ == "__main__":
    unittest.main()
