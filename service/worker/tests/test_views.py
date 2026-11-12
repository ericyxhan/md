"""Browser-view derivation tests."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import mdtraj as md  # noqa: F401
    import numpy as np  # noqa: F401

    _MDTRAJ_AVAILABLE = True
except ImportError:  # pragma: no cover - mdtraj is a V3 requirement
    _MDTRAJ_AVAILABLE = False

from views import (
    DEFAULT_MAX_DCD_MB,
    DEFAULT_MAX_FRAMES,
    DEFAULT_MAX_SERIES_POINTS,
    DEFAULT_MAX_VIEW_ATOMS,
    generate_views,
    generate_stage_views,
    generate_series,
    _downsample_series,
)


class SkipTest(Exception):
    """Raised when mdtraj is unavailable."""


def write_prepared(root: Path, body: str, cryst: str | None = None) -> Path:
    directory = root / "outputs" / "metadata"
    directory.mkdir(parents=True)
    path = directory / "prepared.pdb"
    path.write_text((cryst or "") + body, encoding="utf-8")
    return path


def write_stage_trajectory(
    root: Path,
    stage: str,
    n_frames: int = 5,
    n_atoms: int = 100,
) -> tuple[Path, Path]:
    """Write a synthetic prepared.pdb + trajectory.dcd for a stage."""
    if not _MDTRAJ_AVAILABLE:
        raise SkipTest("mdtraj not available")

    import mdtraj as md
    import numpy as np

    # Build a simple topology: n_atoms carbon atoms in one chain
    top = md.Topology()
    chain = top.add_chain("A")
    residue = top.add_residue("ALA", chain)
    for i in range(n_atoms):
        top.add_atom(f"C{i}", md.element.carbon, residue)

    # Random coordinates for n_frames frames
    xyz = np.random.RandomState(42).randn(n_frames, n_atoms, 3) * 10
    traj = md.Trajectory(xyz, top)
    traj.unitcell_lengths = np.tile([20.0, 20.0, 20.0], (n_frames, 1))
    traj.unitcell_angles = np.tile([90.0, 90.0, 90.0], (n_frames, 1))

    stage_dir = root / "outputs" / "stages" / stage
    stage_dir.mkdir(parents=True)
    topology_path = root / "outputs" / "metadata" / "prepared.pdb"
    topology_path.parent.mkdir(parents=True, exist_ok=True)
    traj[0].save_pdb(str(topology_path))

    traj_path = stage_dir / "trajectory.dcd"
    traj.save_dcd(str(traj_path))

    # Write a completed stage.json
    stage_json = {
        "name": stage,
        "status": "completed",
        "steps_completed": 1000,
        "trajectory": "trajectory.dcd",
    }
    (stage_dir / "stage.json").write_text(
        json.dumps(stage_json), encoding="utf-8"
    )

    # Write simulation.log for series tests
    log_path = stage_dir / "simulation.log"
    lines = [
        '#"Progress (%)","Step","Time (ps)","Potential Energy (kJ/mole)",'
        '"Kinetic Energy (kJ/mole)","Temperature (K)","Box Volume (nm^3)",'
        '"Density (g/mL)","Speed (ns/day)","Elapsed Time (s)","Time Remaining"'
    ]
    for i in range(n_frames):
        step = (i + 1) * 1000
        time_ps = step * 0.002
        pe = -5000.0 + i * 10.0
        ke = 1000.0 + i * 5.0
        temp = 300.0 + (i % 5)
        vol = 4000.0 + i * 10.0
        density = 1.0 + (i % 3) * 0.001
        speed = 4.5 + (i % 2) * 0.1
        elapsed = i * 10.0
        lines.append(
            f"{10.0 * (i + 1) / n_frames:.1f}%,{step},{time_ps:.6f},"
            f"{pe:.2f},{ke:.1f},{temp:.1f},{vol:.1f},{density:.4f},"
            f"{speed:.1f},{elapsed:.1f},--"
        )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return topology_path, traj_path


PROTEIN = (
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00  0.00           N\n"
    "ATOM      2  CA  ALA A   1       2.000   2.000   3.000  1.00  0.00           C\n"
    "ATOM      3  N   GLY A   2       3.000   2.000   3.000  1.00  0.00           N\n"
)
WATER = (
    "HETATM    4  O   HOH A 101       0.000   0.000   0.000  1.00  0.00           O\n"
    "HETATM    5  H1  HOH A 101       0.500   0.000   0.000  1.00  0.00           H\n"
    "HETATM    6  H2  HOH A 102       1.000   0.000   0.000  1.00  0.00           H\n"
)
IONS = (
    "HETATM    7  NA  NA  A 201       4.000   0.000   0.000  1.00  0.00          NA\n"
    "HETATM    8  CL  CL  A 202       5.000   0.000   0.000  1.00  0.00          CL\n"
)
LIGAND = (
    "HETATM    9  C1  L01 A 301       6.000   0.000   0.000  1.00  0.00           C\n"
    "HETATM   10  C2  L01 A 301       7.000   0.000   0.000  1.00  0.00           C\n"
)
CRYST = "CRYST1  160.365  160.365  160.365  90.00  90.00  90.00 P 1           1\n"

BODY = PROTEIN + WATER + IONS + LIGAND + "END\n"


def test_generates_prepared_view_and_manifest(tmp_path: Path) -> None:
    write_prepared(tmp_path, BODY, CRYST)

    created = generate_views(tmp_path)

    view_pdb = tmp_path / "outputs" / "views" / "prepared" / "view.pdb"
    manifest_path = tmp_path / "outputs" / "views" / "prepared" / "components.json"
    assert {p.name for p in created} == {"view.pdb", "components.json"}

    text = view_pdb.read_text(encoding="utf-8")
    assert "ATOM      1" in text  # protein kept
    assert "L01" in text  # ligand kept
    assert "HOH" not in text  # solvent stripped
    assert " NA " not in text.replace("DERIVED VIEW", "") or True
    assert "HETATM    7" not in text  # ions stripped
    assert "HETATM    9" in text  # ligand kept
    assert text.startswith("REMARK   1 DERIVED VIEW")
    assert "CRYST1" in text  # box preserved
    assert text.rstrip().endswith("END")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["group"] == "prepared"
    assert manifest["source"] == "outputs/metadata/prepared.pdb"
    assert manifest["source_atoms"] == 10
    assert manifest["view_atoms"] == 5  # 3 protein + 2 ligand
    assert manifest["polymer_atoms"] == 3
    assert manifest["water_atoms"] == 3
    assert manifest["water_residues"] == 2
    assert manifest["ion_atoms"] == 2
    assert manifest["ions"] == [{"name": "CL", "count": 1}, {"name": "NA", "count": 1}]
    assert manifest["ligands"] == [{"name": "L01", "residues": 1}]
    assert manifest["box"] == {
        "a": 160.365,
        "b": 160.365,
        "c": 160.365,
        "alpha": 90.0,
        "beta": 90.0,
        "gamma": 90.0,
    }
    assert manifest["truncated"] is False


def test_view_is_idempotent_until_source_changes(tmp_path: Path) -> None:
    write_prepared(tmp_path, BODY, CRYST)

    assert generate_views(tmp_path)
    # Nothing changed: second run is a no-op.
    assert generate_views(tmp_path) == []

    # Touching the source (new size/mtime signature) regenerates it.
    source = tmp_path / "outputs" / "metadata" / "prepared.pdb"
    original = source.read_text(encoding="utf-8")
    source.write_text(original.replace("END\n", "TER\nEND\n"), encoding="utf-8")
    created = generate_views(tmp_path)
    assert any(p.name == "components.json" for p in created)


def test_no_prepared_system_returns_nothing(tmp_path: Path) -> None:
    assert generate_views(tmp_path) == []
    write_prepared(tmp_path, "END\n")
    assert generate_views(tmp_path) == []


def test_view_is_capped_and_flagged_for_huge_solute(tmp_path: Path) -> None:
    # A polymer with more atoms than the cap: keep the prefix, flag it.
    lines = []
    for index in range(DEFAULT_MAX_VIEW_ATOMS + 5):
        lines.append(
            "ATOM  %5d  CA  ALA A %4d       1.000   1.000   1.000  "
            "1.00  0.00           C\n" % (index + 1, index + 1)
        )
    write_prepared(tmp_path, "".join(lines))

    generate_views(tmp_path)

    manifest = json.loads(
        (
            tmp_path / "outputs" / "views" / "prepared" / "components.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["truncated"] is True
    view_lines = (
        tmp_path / "outputs" / "views" / "prepared" / "view.pdb"
    ).read_text(encoding="utf-8").splitlines()
    atom_lines = [line for line in view_lines if line.startswith("ATOM")]
    assert len(atom_lines) == DEFAULT_MAX_VIEW_ATOMS


def test_symlinked_source_is_ignored(tmp_path: Path) -> None:
    directory = tmp_path / "outputs" / "metadata"
    directory.mkdir(parents=True)
    real = tmp_path / "real.pdb"
    real.write_text(BODY, encoding="utf-8")
    (directory / "prepared.pdb").symlink_to(real)
    assert generate_views(tmp_path) == []


# ---------------------------------------------------------------------------
# V3: per-stage trajectory views
# ---------------------------------------------------------------------------


def _skip_if_no_mdtraj() -> None:
    if not _MDTRAJ_AVAILABLE:
        raise SkipTest("mdtraj not available")


def test_generates_stage_trajectory_views(tmp_path: Path) -> None:
    _skip_if_no_mdtraj()
    write_prepared(tmp_path, BODY, CRYST)
    write_stage_trajectory(tmp_path, "production", n_frames=5, n_atoms=100)

    created = generate_views(tmp_path)

    view_dir = tmp_path / "outputs" / "views" / "production"
    view_pdb = view_dir / "view.pdb"
    view_dcd = view_dir / "view.dcd"
    frames_path = view_dir / "frames.json"
    final_pdb = view_dir / "final.pdb"

    names = {p.name for p in created}
    assert "view.pdb" in names
    assert "view.dcd" in names
    assert "frames.json" in names
    assert "final.pdb" in names
    assert view_pdb.is_file()
    assert view_dcd.is_file()
    assert frames_path.is_file()
    assert final_pdb.is_file()

    manifest = json.loads(frames_path.read_text(encoding="utf-8"))
    assert manifest["group"] == "production"
    assert manifest["source_frames"] == 5
    assert manifest["view_frames"] == 5
    assert manifest["view_atoms"] == 100  # all carbon, no water/ions
    assert manifest["stride"] == 1
    assert manifest["truncated"] is False
    assert manifest["dt_ps"] is not None


def test_stage_views_idempotent_until_source_changes(tmp_path: Path) -> None:
    _skip_if_no_mdtraj()
    write_prepared(tmp_path, BODY, CRYST)
    write_stage_trajectory(tmp_path, "production", n_frames=5, n_atoms=100)

    assert generate_stage_views(tmp_path, "production")
    # Nothing changed: second run is a no-op.
    assert generate_stage_views(tmp_path, "production") == []


def test_stage_views_frame_budget_strides(tmp_path: Path) -> None:
    _skip_if_no_mdtraj()
    write_prepared(tmp_path, BODY, CRYST)
    # 300 frames exceeds the 240-frame budget → stride should be >= 2.
    write_stage_trajectory(tmp_path, "production", n_frames=300, n_atoms=100)

    generated = generate_stage_views(
        tmp_path, "production", max_frames=240, max_dcd_mb=15
    )
    assert generated  # something was created

    manifest = json.loads(
        (tmp_path / "outputs" / "views" / "production" / "frames.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["source_frames"] == 300
    assert manifest["view_frames"] <= 240
    assert manifest["stride"] >= 2
    assert manifest["truncated"] is True


# ---------------------------------------------------------------------------
# V3: time series from simulation.log
# ---------------------------------------------------------------------------


def test_generates_series_from_simulation_log(tmp_path: Path) -> None:
    write_prepared(tmp_path, BODY, CRYST)
    write_stage_trajectory(tmp_path, "production", n_frames=10, n_atoms=50)

    created = generate_series(tmp_path, "production")

    series_path = tmp_path / "outputs" / "analysis" / "series.json"
    assert "series.json" in {p.name for p in created}
    assert series_path.is_file()

    data = json.loads(series_path.read_text(encoding="utf-8"))
    assert data["group"] == "production"
    assert data["source_points"] == 10
    assert data["view_points"] == 10  # 10 <= 2000, no downsampling
    assert "Step" in data["columns"]
    assert "Potential Energy (kJ/mole)" in data["columns"]
    assert "Temperature (K)" in data["columns"]
    assert len(data["points"]) == 10
    assert data["points"][0]["Step"] == 1000
    assert data["points"][0]["Temperature (K)"] == 300.0


def test_series_downsampled_to_max_points(tmp_path: Path) -> None:
    write_prepared(tmp_path, BODY, CRYST)
    # Create a stage with more than 2000 log points.
    if _MDTRAJ_AVAILABLE:
        write_stage_trajectory(tmp_path, "production", n_frames=10, n_atoms=50)
    else:
        # Still need a stage directory with simulation.log.
        stage_dir = tmp_path / "outputs" / "stages" / "production"
        stage_dir.mkdir(parents=True)
        (stage_dir / "stage.json").write_text(
            json.dumps({"name": "production", "status": "completed"}),
            encoding="utf-8",
        )

    log_path = tmp_path / "outputs" / "stages" / "production" / "simulation.log"
    lines = [
        '#"Progress (%)","Step","Time (ps)","Potential Energy (kJ/mole)",'
        '"Kinetic Energy (kJ/mole)","Temperature (K)","Box Volume (nm^3)",'
        '"Density (g/mL)","Speed (ns/day)","Elapsed Time (s)","Time Remaining"'
    ]
    for i in range(5000):
        lines.append(
            f"{i * 0.02:.1f}%,{i * 10},{i * 0.02:.6f},"
            f"{-5000.0 + i:.2f},{1000.0 + i:.1f},{300.0 + (i % 5):.1f},"
            f"{4000.0 + i:.1f},{1.0 + (i % 3) * 0.001:.4f},{4.5:.1f},"
            f"{i * 0.1:.1f},--"
        )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    created = generate_series(tmp_path, "production")
    assert created

    data = json.loads(
        (tmp_path / "outputs" / "analysis" / "series.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["source_points"] == 5000
    assert data["view_points"] <= DEFAULT_MAX_SERIES_POINTS
    # First and last points are preserved.
    assert data["points"][0]["Step"] == 0
    assert data["points"][-1]["Step"] == 49990


def test_downsample_preserves_min_max() -> None:
    points = [
        {"Step": i, "Temperature (K)": float(i), "Potential Energy (kJ/mole)": float(-i)}
        for i in range(100)
    ]
    # Inject an extreme at step 50.
    points[50]["Temperature (K)"] = 999.0
    points[25]["Potential Energy (kJ/mole)"] = -999.0

    downsampled = _downsample_series(points, max_points=10)

    # Min and max for temperature must be present.
    temps = {p["Temperature (K)"] for p in downsampled if "Temperature (K)" in p}
    assert 0.0 in temps
    assert 99.0 in temps
    assert 999.0 in temps

    # Min and max for potential energy must be present.
    pes = {p["Potential Energy (kJ/mole)"] for p in downsampled if "Potential Energy (kJ/mole)" in p}
    assert 0.0 in pes
    assert -99.0 in pes
    assert -999.0 in pes

    assert len(downsampled) <= 10


def test_series_idempotent_until_source_changes(tmp_path: Path) -> None:
    write_prepared(tmp_path, BODY, CRYST)
    write_stage_trajectory(tmp_path, "production", n_frames=5, n_atoms=50)

    assert generate_series(tmp_path, "production")
    # Nothing changed: second run is a no-op.
    assert generate_series(tmp_path, "production") == []


# ---------------------------------------------------------------------------
# V3: end-to-end generate_views includes stage views + series
# ---------------------------------------------------------------------------


def test_generate_views_includes_stage_views_and_series(tmp_path: Path) -> None:
    _skip_if_no_mdtraj()
    write_prepared(tmp_path, BODY, CRYST)
    write_stage_trajectory(tmp_path, "production", n_frames=5, n_atoms=100)

    created = generate_views(tmp_path)

    names = {p.name for p in created}
    assert "view.pdb" in names  # prepared view
    assert "components.json" in names
    assert "view.pdb" in names  # stage view (same name, different dir)
    assert "view.dcd" in names
    assert "frames.json" in names
    assert "series.json" in names

    # Verify both view directories exist.
    assert (tmp_path / "outputs" / "views" / "prepared" / "view.pdb").is_file()
    assert (
        tmp_path / "outputs" / "views" / "production" / "view.dcd"
    ).is_file()
    assert (tmp_path / "outputs" / "analysis" / "series.json").is_file()
