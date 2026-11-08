"""Stage-manifest and artifact-scan tests."""

from __future__ import annotations

from pathlib import Path

from fakes import write_manifest
from reconcile import (
    artifact_kind,
    read_stage_manifest,
    read_stage_manifests,
    scan_artifacts,
    tail_text,
)


def test_reads_known_stage_manifests(tmp_path: Path) -> None:
    write_manifest(tmp_path, "minimization", steps_completed=0)
    write_manifest(tmp_path, "equil-01", steps_completed=10)
    write_manifest(tmp_path, "unknown", steps_completed=10)

    manifests = read_stage_manifests(
        tmp_path, ["minimization", "equil-01"]
    )
    assert list(manifests) == ["minimization", "equil-01"]
    assert manifests["equil-01"].status == "completed"
    assert manifests["equil-01"].steps_completed == 10
    assert manifests["equil-01"].attempts == 1
    assert read_stage_manifest(tmp_path, "../escape") is None


def test_stage_manifest_symlink_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"status": "completed"}', encoding="utf-8")
    directory = tmp_path / "outputs" / "stages" / "equil-01"
    directory.mkdir(parents=True)
    (directory / "stage.json").symlink_to(outside)
    assert read_stage_manifest(tmp_path, "equil-01") is None


def test_unknown_stage_status_becomes_failed(tmp_path: Path) -> None:
    write_manifest(tmp_path, "equil-01", status="nonsense")
    manifest = read_stage_manifest(tmp_path, "equil-01")
    assert manifest is not None
    assert manifest.status == "failed"


def test_artifact_classification() -> None:
    assert artifact_kind("config.toml") == "config"
    assert artifact_kind("logs/worker.log") == "log"
    assert artifact_kind("logs/simulate.stdout") == "log"
    assert artifact_kind("outputs/stages/equil-01/checkpoint.chk") == "checkpoint"
    assert artifact_kind("outputs/stages/equil-01/trajectory.dcd") == "trajectory"
    assert artifact_kind("outputs/stages/minimization/state.xml") == "state"
    assert artifact_kind("outputs/metadata/prepared.pdb") == "structure"
    assert artifact_kind("outputs/metadata/stage.json") == "metadata"


def test_scan_artifacts_is_confined_and_skips_links(tmp_path: Path) -> None:
    (tmp_path / "outputs" / "stages" / "equil-01").mkdir(parents=True)
    stage = tmp_path / "outputs" / "stages" / "equil-01"
    (stage / "stage.json").write_text("{}", encoding="utf-8")
    (stage / "checkpoint.chk").write_text("chk", encoding="utf-8")
    (tmp_path / "config.toml").write_text("", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "worker.log").write_text("log", encoding="utf-8")
    (tmp_path / "partial.tmp").write_text("tmp", encoding="utf-8")

    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape.txt").symlink_to(outside)
    (tmp_path / "linked-dir").symlink_to(tmp_path / "logs")

    artifacts = scan_artifacts(tmp_path, ["equil-01"], max_files=100)
    paths = [item.relative_path for item in artifacts]
    assert "escape.txt" not in paths
    assert "partial.tmp" not in paths
    assert "linked-dir/worker.log" not in paths
    assert "config.toml" in paths
    assert "logs/worker.log" in paths

    stage_json = next(
        item for item in artifacts if item.relative_path.endswith("stage.json")
    )
    assert stage_json.stage_name == "equil-01"
    assert stage_json.kind == "metadata"
    checkpoint = next(
        item for item in artifacts if item.relative_path.endswith(".chk")
    )
    assert checkpoint.kind == "checkpoint"

    limited = scan_artifacts(tmp_path, ["equil-01"], max_files=2)
    assert len(limited) == 2


def test_tail_text_returns_the_end(tmp_path: Path) -> None:
    path = tmp_path / "simulate.stderr"
    text = "a" * 100 + "THE END"
    path.write_text(text, encoding="utf-8")
    assert tail_text(path, max_chars=20) == text[-20:]
    assert tail_text(tmp_path / "missing") == ""
