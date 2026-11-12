"""The shared values must agree across every file that copies them.

``service/contract.env`` owns the ports, the service account, the mount paths
and the route prefixes.  ``service/scripts/check-contract.py`` verifies that
compose.yml, the Caddyfile, the Dockerfiles, the nginx config, the systemd
units and the frontend still agree with it.

These tests skip when only the API package is present, which is the case
inside the API image.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).resolve().parents[2]
CHECKER = SERVICE_DIR / "scripts" / "check-contract.py"

# The files the checker reads.  They are copied into a scratch tree so the
# self-test can perturb one and confirm the checker notices.
CONTRACT_FILES = (
    "contract.env",
    "compose.yml",
    "Caddyfile",
    "api/Dockerfile",
    "worker/prep_worker.Dockerfile",
    "web/Dockerfile",
    "web/nginx.conf",
    "api/app/main.py",
    "api/app/routers/internal.py",
    "web/src/lib/api.ts",
    "scripts/md-funnel.service",
    "scripts/check-contract.py",
)

pytestmark = pytest.mark.skipif(
    not CHECKER.exists(),
    reason="the service tree is not available (running inside the API image?)",
)


def _run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "check-contract.py")],
        capture_output=True,
        text=True,
        check=False,
    )


def test_shared_values_agree() -> None:
    result = _run_checker(SERVICE_DIR)
    assert result.returncode == 0, result.stdout + result.stderr


def _scratch_tree(tmp_path: Path) -> Path:
    """Copy the files the checker reads into a scratch directory."""

    root = tmp_path / "service"
    for relative in CONTRACT_FILES:
        source = SERVICE_DIR / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_checker_detects_a_drifted_contract(tmp_path: Path) -> None:
    """Changing one value without the others must fail the check."""

    root = _scratch_tree(tmp_path)
    contract = root / "contract.env"
    contract.write_text(
        contract.read_text().replace(
            "MD_EDGE_PORT=8080", "MD_EDGE_PORT=9999"
        )
    )

    result = _run_checker(root)
    assert result.returncode != 0, result.stdout
    assert "MD_EDGE_PORT" in result.stdout


def test_checker_detects_a_drifted_copy(tmp_path: Path) -> None:
    """Changing a copy without the contract must fail the check."""

    root = _scratch_tree(tmp_path)
    caddyfile = root / "Caddyfile"
    caddyfile.write_text(
        caddyfile.read_text().replace(
            ":{$MD_EDGE_PORT:8080}", ":{$MD_EDGE_PORT:9443}"
        )
    )

    result = _run_checker(root)
    assert result.returncode != 0, result.stdout
    assert "MD_EDGE_PORT" in result.stdout


def test_checker_detects_a_drifted_service_account(tmp_path: Path) -> None:
    """A container running as a different account must fail the check."""

    root = _scratch_tree(tmp_path)
    dockerfile = root / "worker" / "prep_worker.Dockerfile"
    dockerfile.write_text(
        dockerfile.read_text().replace(
            "USER ${MD_SERVICE_UID}:${MD_SERVICE_GID}", "USER 10002:10002"
        )
    )

    result = _run_checker(root)
    assert result.returncode != 0, result.stdout
    assert "account" in result.stdout
