"""Config builder and request-policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config_builder import build_config_toml, write_config
from app.policies import build_canonical_spec, stage_names
from app.schemas import JobCreate
from app.settings import Settings
from app.simulation_config import load_workflow_config


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_root=tmp_path,
        simulation_platform="CPU",
    )


def _canonical(request: JobCreate, settings: Settings, inputs: dict | None = None):
    return build_canonical_spec(
        request,
        inputs
        or {
            "mode": "complex",
            "complex": "inputs/complex.pdb",
            "display_name": "complex.pdb",
        },
        settings,
    )


def test_complex_job_generates_valid_config(settings: Settings, tmp_path: Path) -> None:
    request = JobCreate.model_validate(
        {
            "name": "complex job",
            "input": {"mode": "complex", "complex_file_id": "file-1"},
            "equilibration": [
                {"duration_ps": 0.02, "integrator": {"type": "langevin_middle"}},
                {"duration_ps": 0.04, "barostat": {"type": "none"}},
            ],
            "production": {
                "enabled": True,
                "duration_ns": 0.001,
                "trajectory_interval": 0,
                "barostat": {
                    "type": "monte_carlo",
                    "pressure_bar": 1.0,
                    "temperature_k": 300.0,
                },
            },
        }
    )
    canonical = _canonical(request, settings)
    assert stage_names(canonical) == [
        "minimization",
        "equil-01",
        "equil-02",
        "production",
    ]
    assert canonical["equilibration"][0]["steps"] == 10
    assert canonical["equilibration"][1]["steps"] == 20
    assert canonical["production"]["steps"] == 500

    job_root = tmp_path / "jobs" / "job-1"
    job_root.mkdir(parents=True)
    path = write_config(canonical, job_root, settings)
    config = load_workflow_config(path)
    assert config.run.output_dir == job_root / "outputs"
    assert config.run.platform == "CPU"
    assert config.input.complex_path == job_root / "inputs" / "complex.pdb"
    assert [stage.name for stage in config.equilibration] == [
        "equil-01",
        "equil-02",
    ]
    assert config.production is not None
    assert config.production.steps == 500
    assert config.production.trajectory_report_interval is None


def test_protein_ligands_without_production(settings: Settings, tmp_path: Path) -> None:
    request = JobCreate.model_validate(
        {
            "name": "protein ligands",
            "input": {
                "mode": "protein_ligands",
                "protein_file_id": "protein-1",
                "ligand_file_ids": ["ligand-1", "ligand-2"],
            },
            "minimization": {"enabled": False},
            "equilibration": [
                {"steps": 5, "integrator": {"type": "verlet"}},
            ],
            "production": {"enabled": False},
        }
    )
    canonical = _canonical(
        request,
        settings,
        {
            "mode": "protein_ligands",
            "protein": "inputs/protein.pdb",
            "ligands": ["inputs/ligand-01.sdf", "inputs/ligand-02.sdf"],
        },
    )
    assert stage_names(canonical) == ["equil-01"]

    job_root = tmp_path / "jobs" / "job-2"
    job_root.mkdir(parents=True)
    config = load_workflow_config(write_config(canonical, job_root, settings))
    assert config.minimization.enabled is False
    assert config.production is None
    assert config.input.protein_path == job_root / "inputs" / "protein.pdb"
    assert config.input.ligand_paths == (
        job_root / "inputs" / "ligand-01.sdf",
        job_root / "inputs" / "ligand-02.sdf",
    )


def test_pdb_id_input_is_written_as_a_local_complex(
    settings: Settings, tmp_path: Path
) -> None:
    request = JobCreate.model_validate(
        {
            "name": "pdb",
            "input": {"mode": "pdb_id", "pdb_id": "7YAE"},
            "equilibration": [{"steps": 1}],
        }
    )
    canonical = _canonical(
        request,
        settings,
        {
            "mode": "pdb_id",
            "pdb_id": "7YAE",
            "complex": "inputs/complex.pdb",
        },
    )
    job_root = tmp_path / "jobs" / "job-3"
    job_root.mkdir(parents=True)
    text = build_config_toml(canonical, job_root, settings)
    assert "pdb_id =" not in text
    assert "complex.pdb" in text


def test_all_integrator_types_produce_valid_toml(
    settings: Settings, tmp_path: Path
) -> None:
    integrators = [
        ("langevin_middle", {"duration_ps": 0.02}),
        ("langevin", {"duration_ps": 0.02}),
        ("brownian", {"duration_ps": 0.02}),
        ("verlet", {"duration_ps": 0.02}),
        ("nose_hoover", {"duration_ps": 0.02}),
        ("variable_verlet", {"steps": 10, "integrator": {"type": "variable_verlet"}}),
        (
            "variable_langevin",
            {"steps": 10, "integrator": {"type": "variable_langevin"}},
        ),
    ]
    for kind, overrides in integrators:
        stage = {"integrator": {"type": kind}}
        stage.update(overrides)
        request = JobCreate.model_validate(
            {
                "name": kind,
                "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
                "equilibration": [stage],
            }
        )
        job_root = tmp_path / "jobs" / kind
        job_root.mkdir(parents=True)
        canonical = _canonical(
            request,
            settings,
            {
                "mode": "pdb_id",
                "pdb_id": "1ABC",
                "complex": "inputs/complex.pdb",
            },
        )
        config = load_workflow_config(
            write_config(canonical, job_root, settings)
        )
        assert config.equilibration[0].integrator.type == kind


def test_unknown_keys_and_unsafe_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {
                "name": "bad",
                "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
                "equilibration": [{"steps": 10}],
                "output_dir": "/etc",
            }
        )
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {
                "name": "bad",
                "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
                "equilibration": [
                    {
                        "steps": 10,
                        "integrator": {"type": "verlet", "platform": "CUDA"},
                    }
                ],
            }
        )


def test_variable_step_stage_requires_steps() -> None:
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {
                "name": "bad",
                "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
                "equilibration": [
                    {
                        "duration_ps": 1.0,
                        "integrator": {"type": "variable_verlet"},
                    }
                ],
            }
        )


def test_stage_and_total_step_limits(settings: Settings) -> None:
    settings.max_steps_per_stage = 10
    with pytest.raises(Exception) as stage_error:
        request = JobCreate.model_validate(
            {
                "name": "long",
                "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
                "equilibration": [{"steps": 11}],
            }
        )
        _canonical(request, settings)
    assert "stage_too_long" in str(stage_error.value) or "step" in str(
        stage_error.value
    )

    settings.max_steps_per_stage = 20
    settings.max_total_steps = 20
    request = JobCreate.model_validate(
        {
            "name": "long",
            "input": {"mode": "pdb_id", "pdb_id": "1ABC"},
            "equilibration": [{"steps": 10}, {"steps": 10}, {"steps": 10}],
        }
    )
    with pytest.raises(Exception) as total_error:
        _canonical(request, settings)
    assert "total" in str(total_error.value).lower() or "job_too_long" in str(
        total_error.value
    )
