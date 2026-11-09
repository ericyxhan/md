"""Capability discovery for frontends."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..policies import (
    BAROSTAT_TYPES,
    FIXED_FORCEFIELDS,
    INPUT_MODES,
    INTEGRATOR_TYPES,
    LIGAND_FORCEFIELD,
)
from ..schemas import (
    IntegratorSpec,
    JobCreate,
    MinimizationSpec,
    ParameterizationSpec,
    ProductionSpec,
    StageSpec,
)
from ..security import require_owner
from ..settings import get_settings
from ..storage import ALLOWED_SUFFIXES, LIGAND_SUFFIXES, PROTEIN_SUFFIXES

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities")
def capabilities(
    request: Request,
    _owner: str = Depends(require_owner),
) -> dict:
    settings = request.app.state.settings
    return {
        "api_version": "v1",
        "input_modes": list(INPUT_MODES),
        "input_formats": {
            "protein": sorted(PROTEIN_SUFFIXES),
            "ligand": sorted(LIGAND_SUFFIXES),
            "all": sorted(ALLOWED_SUFFIXES),
        },
        "integrators": list(INTEGRATOR_TYPES),
        "barostats": list(BAROSTAT_TYPES),
        "fixed_forcefields": list(FIXED_FORCEFIELDS),
        "ligand_forcefield": LIGAND_FORCEFIELD,
        "defaults": {
            "parameterization": ParameterizationSpec().model_dump(mode="json"),
            "minimization": MinimizationSpec().model_dump(mode="json"),
            "equilibration": StageSpec(
                duration_ps=20.0
            ).model_dump(mode="json"),
            "production": ProductionSpec(
                enabled=True, duration_ns=0.1
            ).model_dump(mode="json"),
            "integrations": IntegratorSpec().model_dump(mode="json"),
            "job": {
                "equilibration_stages": 1,
                "production_enabled": True,
            },
        },
        "limits": {
            "max_upload_bytes": settings.max_upload_bytes,
            "max_job_upload_bytes": settings.max_job_upload_bytes,
            "max_ligands": settings.max_ligands,
            "max_equilibration_stages": settings.max_equilibration_stages,
            "max_steps_per_stage": settings.max_steps_per_stage,
            "max_total_steps": settings.max_total_steps,
            "max_queued_jobs_per_owner": settings.max_queued_jobs_per_owner,
            "min_free_disk_bytes": settings.min_free_disk_bytes,
            "retention_days": settings.retention_days,
            "rate_limit_requests_per_minute": (
                settings.rate_limit_requests_per_minute
            ),
            "max_name_length": 200,
            "max_stage_retries": 3,
        },
        "pdb_download_enabled": settings.allow_pdb_download,
        "simulation_platform": settings.simulation_platform,
        "prep_workflows": {
            "membrane_embed": {
                "enabled": bool(settings.packmol_path),
                "lipids": ["POPC", "POPE", "DPPC", "DLPC", "DSPC", "SOPC"],
                "max_box_padding_nm": 5.0,
                "supported_input_formats": [".pdb", ".cif", ".mmcif"],
            }
        },
    }
