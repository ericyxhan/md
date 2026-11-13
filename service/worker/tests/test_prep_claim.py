"""The prep worker validates the claim before it touches the filesystem.

The API supplies absolute paths because the worker mounts the same data
root.  An API bug or a compromised API must not be able to point the worker
at an arbitrary directory, so the workspace has to be exactly the one the
account's preparation owns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from prep_config import PrepConfig
from prep_worker import ClaimError, PrepWorker

OWNER_ID = "00000000-0000-4000-8000-0000000000aa"
PREP_JOB_ID = "prep-1"


def _config(data_root: Path) -> PrepConfig:
    return PrepConfig(
        api_url="http://api:8000/internal/v1/prep",
        token="worker-token",
        worker_id="prep-worker",
        hostname="worker",
        packmol_path="/usr/bin/packmol",
        data_root=data_root,
    )


def _worker(data_root: Path) -> PrepWorker:
    return PrepWorker(_config(data_root), client=None)


def _claim(data_root: Path, **overrides) -> dict:
    work_dir = data_root / "users" / OWNER_ID / "prep" / PREP_JOB_ID
    source = work_dir / "input.pdb"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("HEADER\nEND\n", encoding="utf-8")

    claim = {
        "prep_job_id": PREP_JOB_ID,
        "run_token": "11111111-2222-4333-8444-555555555555",
        "owner_id": OWNER_ID,
        "job_type": "system_prep",
        "steps": [{"operation": "add_solvent"}],
        "source_path": str(source),
        "work_dir": str(work_dir),
    }
    claim.update(overrides)
    return claim


def test_a_claim_for_the_accounts_own_workspace_is_accepted(
    tmp_path: Path,
) -> None:
    worker = _worker(tmp_path)

    claim = worker._parse_claim(_claim(tmp_path))

    assert claim.prep_job_id == PREP_JOB_ID
    assert claim.work_dir == (
        tmp_path / "users" / OWNER_ID / "prep" / PREP_JOB_ID
    )


def test_a_workspace_outside_the_accounts_tree_is_refused(
    tmp_path: Path,
) -> None:
    worker = _worker(tmp_path)
    elsewhere = tmp_path / "somewhere-else"
    elsewhere.mkdir()

    with pytest.raises(ClaimError, match="outside"):
        worker._parse_claim(_claim(tmp_path, work_dir=str(elsewhere)))


def test_another_accounts_workspace_is_refused(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    other_owner = "00000000-0000-4000-8000-0000000000bb"

    with pytest.raises(ClaimError, match="outside"):
        worker._parse_claim(
            _claim(tmp_path, owner_id=other_owner)
        )


def test_a_claim_without_an_owner_is_refused(tmp_path: Path) -> None:
    worker = _worker(tmp_path)
    claim = _claim(tmp_path)
    del claim["owner_id"]

    with pytest.raises(ClaimError, match="owner_id"):
        worker._parse_claim(claim)


def test_a_claim_with_a_malformed_owner_is_refused(tmp_path: Path) -> None:
    worker = _worker(tmp_path)

    with pytest.raises(ClaimError, match="owner id"):
        worker._parse_claim(_claim(tmp_path, owner_id="../escape"))


def test_a_relative_workspace_is_refused(tmp_path: Path) -> None:
    worker = _worker(tmp_path)

    with pytest.raises(ClaimError, match="absolute"):
        worker._parse_claim(_claim(tmp_path, work_dir="relative/path"))
