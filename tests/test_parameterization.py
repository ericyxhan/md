"""Parameterizer command and fingerprint tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from config import load_config
from parameterization import (
    InputFiles,
    build_parameterizer_command,
    parameterization_fingerprint,
)


class ParameterizationTests(unittest.TestCase):
    def _write_config(
        self,
        directory: Path,
        *,
        ligand_charges: str = "",
        preparation_flags: str = "",
    ) -> Path:
        path = directory / "config.toml"
        path.write_text(
            f"""
[input]
complex = "input.pdb"

[parameterization]
python = "{Path(sys.executable)}"
{preparation_flags}

[parameterization.ligand_charges]
{ligand_charges}

[production]
steps = 10

[production.integrator]
type = "langevin_middle"

[production.barostat]
type = "none"
""",
            encoding="utf-8",
        )
        return path

    def test_preparation_settings_are_passed_to_the_parameterizer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            complex_path = directory / "input.pdb"
            complex_path.write_text("HEADER test\n", encoding="utf-8")
            config = load_config(
                self._write_config(
                    directory,
                    ligand_charges="L01 = -1\nL02 = 0",
                    preparation_flags=(
                        "strip_existing_hydrogens = false\n"
                        "replace_nonstandard_residues = false\n"
                        "strip_crystallographic_waters = true\n"
                        'strip_residues = ["SO4", "GOL"]'
                    ),
                )
            )

            command = build_parameterizer_command(
                config,
                InputFiles(kind="complex", complex_path=complex_path),
                directory / "outputs",
            )

            self.assertIn("--keep-existing-hydrogens", command)
            self.assertIn("--keep-nonstandard-residues", command)
            self.assertIn("--strip-waters", command)
            strip_index = command.index("--strip-residue")
            self.assertEqual(command[strip_index + 1], "SO4")
            self.assertEqual(command[strip_index + 3], "GOL")
            ligand_charge_index = command.index("--ligand-charge")
            self.assertEqual(command[ligand_charge_index + 1], "L01=-1")
            self.assertEqual(command[ligand_charge_index + 3], "L02=0")

    def test_ligand_charges_change_the_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            complex_path = directory / "input.pdb"
            complex_path.write_text("HEADER test\n", encoding="utf-8")
            input_files = InputFiles(kind="complex", complex_path=complex_path)
            config_path = self._write_config(directory)
            without_charges = parameterization_fingerprint(
                load_config(config_path), input_files
            )

            self._write_config(directory, ligand_charges="L01 = -1")
            with_charges = parameterization_fingerprint(
                load_config(config_path), input_files
            )

            self.assertNotEqual(without_charges, with_charges)

    def test_strip_settings_change_the_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            complex_path = directory / "input.pdb"
            complex_path.write_text("HEADER test\n", encoding="utf-8")
            input_files = InputFiles(kind="complex", complex_path=complex_path)
            config_path = self._write_config(directory)
            without_stripping = parameterization_fingerprint(
                load_config(config_path), input_files
            )

            self._write_config(
                directory,
                preparation_flags=(
                    "strip_crystallographic_waters = true\n"
                    'strip_residues = ["SO4"]'
                ),
            )
            with_stripping = parameterization_fingerprint(
                load_config(config_path), input_files
            )

            self.assertNotEqual(without_stripping, with_stripping)


if __name__ == "__main__":
    unittest.main()
