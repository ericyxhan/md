"""Post-run trajectory analysis for an MD job.

Runs after ``simulate.py`` exits and before the worker reports finish.  All
work is best-effort: a failure here is logged but never fails the job, since
analysis is a derived artifact.

Outputs (under ``<job_root>/outputs/analysis/``):
  - structure_series.json : per-frame RMSD, Rg, H-bond count, secondary-structure
    fractions, SASA (downsampled like series.json).
  - rmsf.json            : per-residue C-alpha RMSF over the whole trajectory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _find_topology(job_root: Path) -> Path | None:
    candidates = [
        job_root / "outputs" / "metadata" / "prepared.pdb",
        job_root / "outputs" / "inputs" / "prepared.pdb",
        job_root / "inputs" / "prepared.pdb",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # fallback: any pdb under metadata/inputs
    for sub in ("outputs/metadata", "outputs/inputs", "inputs"):
        d = job_root / sub
        if d.is_dir():
            for p in sorted(d.glob("*.pdb")):
                return p
    return None


def _find_trajectory(job_root: Path) -> Path | None:
    stages_dir = job_root / "outputs" / "stages"
    if not stages_dir.is_dir():
        return None
    # prefer production, then last completed stage
    for name in ("production",):
        p = stages_dir / name / "trajectory.dcd"
        if p.is_file():
            return p
    # fall back to the last stage dir that has a trajectory.dcd
    dirs = sorted(d for d in stages_dir.iterdir() if d.is_dir())
    for d in reversed(dirs):
        p = d / "trajectory.dcd"
        if p.is_file():
            return p
    return None


def _downsample(n: int, max_points: int = 2000) -> list[int]:
    if n <= max_points:
        return list(range(n))
    # preserve first, last, and evenly spaced; also keep min/max via stride
    step = max(1, n // max_points)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def run_analysis(job_root: Path, log) -> list[Path]:
    """Compute trajectory analysis and write outputs. Returns list of written paths."""

    written: list[Path] = []
    try:
        import mdtraj as md
        import numpy as np
    except Exception as exc:
        log(f"analysis skipped: mdtraj not available ({exc})")
        return written

    top_path = _find_topology(job_root)
    traj_path = _find_trajectory(job_root)
    if top_path is None or traj_path is None:
        log("analysis skipped: no topology or trajectory found")
        return written

    out_dir = job_root / "outputs" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        traj = md.load(str(traj_path), top=str(top_path))
    except Exception as exc:
        log(f"analysis failed to load trajectory: {exc}")
        return written

    if traj.n_frames < 2:
        log("analysis skipped: fewer than 2 frames")
        return written

    try:
        solute_idx = traj.topology.select("not water")
        if len(solute_idx) == 0:
            solute_idx = None
        ts = traj.atom_slice(solute_idx) if solute_idx is not None else traj
    except Exception as exc:
        log(f"analysis failed to slice solute: {exc}")
        ts = traj

    # backbone selection for RMSD
    try:
        bb_idx = ts.topology.select("name CA")
        if len(bb_idx) == 0:
            bb_idx = None
    except Exception:
        bb_idx = None

    frames = list(range(ts.n_frames))
    idxs = _downsample(ts.n_frames)

    # RMSD vs frame 0
    try:
        rmsd = md.rmsd(ts, ts, 0, atom_indices=bb_idx) if bb_idx is not None and len(bb_idx) > 0 else None
    except Exception as exc:
        log(f"rmsd failed: {exc}")
        rmsd = None

    # Rg
    try:
        rg = md.compute_rg(ts)
    except Exception as exc:
        log(f"rg failed: {exc}")
        rg = None

    # H-bonds count per frame (baker_hubbard per frame; capped to sampled frames)
    hb_count = None
    try:
        counts = []
        for i in idxs:
            frame = ts[i]
            pairs = md.baker_hubbard(frame)
            counts.append(float(len(pairs)))
        # expand back to full frame count for indexing by idxs
        full = [0.0] * ts.n_frames
        for k, i in enumerate(idxs):
            full[i] = counts[k]
        hb_count = full
    except Exception as exc:
        log(f"hbonds failed: {exc}")
        hb_count = None

    # DSSP secondary structure fractions
    helix_frac = None
    sheet_frac = None
    try:
        dssp = md.compute_dssp(ts, simplified=True)
        helix_frac = (dssp == "H").mean(axis=1).astype(float)
        sheet_frac = (dssp == "E").mean(axis=1).astype(float)
    except Exception as exc:
        log(f"dssp failed: {exc}")

    # SASA total per frame
    try:
        sasa = md.shrake_rupley(ts)
        sasa_total = sasa.sum(axis=1).astype(float)
    except Exception as exc:
        log(f"sasa failed: {exc}")
        sasa_total = None

    # RMSF per residue (CA) — compute on all frames, store separately
    try:
        if bb_idx is not None and len(bb_idx) > 0:
            rmsf = md.rmsf(ts, ts, 0, atom_indices=bb_idx)
            # map to residue indices
            from collections import defaultdict
            agg: dict[int, list[float]] = defaultdict(list)
            for a, r in zip(bb_idx, rmsf):
                agg[ts.topology.atom(a).residue.index].append(float(r))
            rmsf_per_residue = {}
            for k, v in agg.items():
                res = ts.topology.residue(k)
                label = f"{res.chain.id}:{res.resSeq} {res.name}"
                rmsf_per_residue[label] = float(sum(v) / len(v))
            rmsf_path = out_dir / "rmsf.json"
            rmsf_path.write_text(json.dumps({"residue_rmsf_nm": rmsf_per_residue}, indent=2))
            written.append(rmsf_path)
    except Exception as exc:
        log(f"rmsf failed: {exc}")

    # Build series points
    # time per frame: try traj.time (ps) else index
    times = None
    try:
        times = traj.time
    except Exception:
        times = None

    points = []
    for i in idxs:
        pt: dict[str, Any] = {"frame": int(i)}
        if times is not None:
            try:
                pt["time_ps"] = float(times[i])
            except Exception:
                pass
        if rmsd is not None:
            pt["rmsd_nm"] = float(rmsd[i])
        if rg is not None:
            pt["rg_nm"] = float(rg[i])
        if hb_count is not None:
            pt["hbonds"] = float(hb_count[i])
        if helix_frac is not None:
            pt["helix_fraction"] = float(helix_frac[i])
        if sheet_frac is not None:
            pt["sheet_fraction"] = float(sheet_frac[i])
        if sasa_total is not None:
            pt["sasa_nm2"] = float(sasa_total[i])
        points.append(pt)

    series = {
        "source_frames": int(ts.n_frames),
        "view_frames": len(points),
        "columns": list(points[0].keys()) if points else [],
        "points": points,
    }
    series_path = out_dir / "structure_series.json"
    series_path.write_text(json.dumps(series, indent=2))
    written.append(series_path)
    log(f"analysis wrote {len(written)} files ({len(points)} frames)")
    return written

