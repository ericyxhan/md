"""Configuration parsing tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def _write_config(self, directory: Path, text: str) -> Path:
        path = directory / "config.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_config_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            config = load_config(config_path)

            self.assertEqual(config.run.output_dir, directory / "outputs")
            self.assertEqual(config.input.complex_path, directory / "input.pdb")
            self.assertEqual(config.production.steps, 10)
            self.assertEqual(config.production.integrator.type, "langevin_middle")

    def test_duration_is_converted_to_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[[equilibration]]
name = "nvt"
duration_ps = 0.020

[equilibration.integrator]
type = "langevin_middle"
timestep_ps = 0.002

[equilibration.barostat]
type = "none"

[production]
duration_ns = 0.001

[production.integrator]
type = "verlet"
timestep_ps = 0.001

[production.barostat]
type = "none"
""",
            )

            config = load_config(config_path)

            self.assertEqual(config.equilibration[0].steps, 10)
            self.assertEqual(config.production.steps, 1000)

    def test_monte_carlo_barostat_inherits_integrator_temperature(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[[equilibration]]
name = "npt"
steps = 10

[equilibration.integrator]
type = "langevin_middle"
temperature_k = 310.0

[equilibration.barostat]
type = "monte_carlo"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            config = load_config(config_path)
            stage = config.equilibration[0]

            self.assertEqual(stage.barostat.temperature_k, 310.0)
            self.assertEqual(stage.integrator.temperature_k, 310.0)

    def test_trajectory_interval_zero_disables_dcd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[production]
steps = 10
report_interval = 5
trajectory_interval = 0

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            config = load_config(config_path)

            self.assertEqual(config.production.report_interval, 5)
            self.assertIsNone(config.production.trajectory_report_interval)

    def test_trajectory_interval_defaults_to_report_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[production]
steps = 10
report_interval = 5

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            config = load_config(config_path)

            self.assertEqual(config.production.trajectory_report_interval, 5)

    def test_negative_trajectory_interval_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[production]
steps = 10
trajectory_interval = -1

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_unknown_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[run]
platfrom = "CPU"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("unknown key", str(context.exception))

    def test_exactly_one_input_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"
protein = "protein.pdb"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError):
                load_config(config_path)

    def test_duration_requires_fixed_step_integrator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[[equilibration]]
name = "variable"
duration_ps = 10.0

[equilibration.integrator]
type = "variable_verlet"

[equilibration.barostat]
type = "none"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("fixed-step", str(context.exception))

    def test_duplicate_stage_names_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[[equilibration]]
name = "same"
steps = 10

[equilibration.integrator]
type = "langevin_middle"

[equilibration.barostat]
type = "none"

[production]
name = "same"
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("unique", str(context.exception))

    def test_parameterization_preparation_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            parameterization = load_config(config_path).parameterization

            self.assertEqual(parameterization.ligand_charges, ())
            self.assertTrue(parameterization.strip_existing_hydrogens)
            self.assertTrue(parameterization.replace_nonstandard_residues)
            self.assertFalse(parameterization.strip_crystallographic_waters)
            self.assertEqual(parameterization.strip_residues, ())

    def test_ligand_charges_are_parsed_and_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[parameterization]
strip_existing_hydrogens = false
replace_nonstandard_residues = false
strip_crystallographic_waters = true
strip_residues = [" so4 ", "NA", "SO4", "gol"]

[parameterization.ligand_charges]
L02 = 0
L01 = -1

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            parameterization = load_config(config_path).parameterization

            self.assertEqual(
                parameterization.ligand_charges,
                (("L01", -1), ("L02", 0)),
            )
            self.assertFalse(parameterization.strip_existing_hydrogens)
            self.assertFalse(parameterization.replace_nonstandard_residues)
            self.assertTrue(parameterization.strip_crystallographic_waters)
            self.assertEqual(
                parameterization.strip_residues,
                ("SO4", "NA", "GOL"),
            )

    def test_non_integer_ligand_charge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[parameterization.ligand_charges]
L01 = -0.5

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("integer net charge", str(context.exception))

    def test_empty_ligand_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[parameterization.ligand_charges]
" " = 0

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("invalid ligand name", str(context.exception))

    def test_strip_residues_must_be_an_array(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path = self._write_config(
                directory,
                """
[input]
complex = "input.pdb"

[parameterization]
strip_residues = "SO4"

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            )

            with self.assertRaises(ConfigError) as context:
                load_config(config_path)
            self.assertIn("strip_residues", str(context.exception))


if __name__ == "__main__":
    unittest.main()
