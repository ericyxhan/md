"""Progress-file parsing tests."""

from __future__ import annotations

from pathlib import Path

from progress import read_progress


def test_reads_and_normalizes_progress(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    path.write_text(
        """
        {
          "phase": "simulating",
          "status": "running",
          "stage": "equil-01",
          "step": 25,
          "total_steps": 100,
          "percent": 25.0,
          "updated_at": "2026-11-07T12:00:00Z",
          "error": null
        }
        """,
        encoding="utf-8",
    )

    snapshot = read_progress(path)
    assert snapshot is not None
    assert snapshot.api_phase == "simulating"
    assert snapshot.change_key == ("simulating", "equil-01", 25, 100)
    assert snapshot.api_payload("token") == {
        "run_token": "token",
        "phase": "simulating",
        "stage": "equil-01",
        "step": 25,
        "total_steps": 100,
        "percent": 25.0,
        "updated_at": "2026-11-07T12:00:00Z",
    }


def test_maps_lifecycle_phases_to_api_phases(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    for raw, expected in (
        ("starting", "parameterizing"),
        ("minimizing", "minimizing"),
        ("production", "simulating"),
        ("completed", "finalizing"),
    ):
        path.write_text(f'{{"phase": "{raw}"}}', encoding="utf-8")
        snapshot = read_progress(path)
        assert snapshot is not None
        assert snapshot.api_phase == expected


def test_derives_percent_and_ignores_invalid_values(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    path.write_text(
        '{"phase": "simulating", "step": 5, "total_steps": 10, '
        '"percent": "not-a-number"}',
        encoding="utf-8",
    )
    snapshot = read_progress(path)
    assert snapshot is not None
    assert snapshot.percent is None
    assert snapshot.api_payload("t")["percent"] == 50.0

    path.write_text('{"phase": "simulating", "step": -4}', encoding="utf-8")
    snapshot = read_progress(path)
    assert snapshot is not None
    assert snapshot.step == 0


def test_absent_corrupt_and_symlink_progress_are_ignored(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert read_progress(missing) is None

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert read_progress(corrupt) is None

    valid = tmp_path / "valid.json"
    valid.write_text('{"phase": "simulating"}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(valid)
    assert read_progress(link) is None
