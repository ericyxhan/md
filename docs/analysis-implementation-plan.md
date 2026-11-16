# Analysis — current state and implementation plan

## What MolDy provides today (after a completed run)

Source: `service/web/src/components/analysis/AnalysisPanel.tsx`,
`service/api/app/routers/jobs.py` (`get_views`, `get_job_series`).

1. **System composition** (from the derived view manifest): solute atoms, system
   atoms, waters removed, ions, box dimensions (a×b×c), truncation flag.
2. **Time series** (from `simulation.log` via `outputs/analysis/series.json`,
   downsampled to ≤2000 points with min/max preserved): step, time, potential
   energy, kinetic energy, temperature, density, volume, speed, elapsed.
3. **Charts rendered:** Temperature, Density, Potential Energy, Box Volume,
   (now also Kinetic Energy and Speed).
4. **Trajectory playback** via Mol* (derived solute-focused view PDB + DCD).

## What is missing (the gap a lab user would notice)

Structural/trajectory analysis that a typical MD user expects and that is
**not** currently computed anywhere in the pipeline:

- RMSD (vs. starting structure, vs. reference)
- RMSF (per-residue fluctuation)
- Radius of gyration (Rg) over time
- Hydrogen-bond counts / occupancy
- Contact maps / salt bridges
- Secondary-structure time series
- Per-residue energy decomposition
- Cluster analysis of poses/trajectory

The worker only writes `simulation.log` (OpenMM `StateDataReporter`), which
contains thermodynamic state, not structural metrics. Structural metrics
require analyzing the DCD trajectory, which is not done.

## Plan

### Phase A1 — extend the series (low effort, high value)
The StateDataReporter already logs PE/KE/T/V/density/speed. Add to the
worker's series writer the running min/max/mean of each, plus a derived
"equilibration indicator" (e.g., rolling std of temperature). Add charts for
KE and speed (done). Add a "Time" x-axis toggle.

### Phase A2 — lightweight structural metrics in the worker
Use RDKit (already in the param env) or a small pure-Python trajectory
reader to compute, per frame, on the *solute view* (already derived):
- RMSD vs. frame 0
- Radius of gyration
- (optional) per-residue RMSF (requires all frames in memory — heavy)

Write to `outputs/analysis/structure_series.json` with the same downsampled
format as `series.json`. Add a new `ViewKind`/artifact kind `analysis` and a
`/analysis/structure-series` endpoint mirroring `get_job_series`.

Frontend: add RMSD and Rg charts to `AnalysisPanel`.

### Phase A3 — heavy analysis as opt-in post-processing
RMSF, H-bonds, contacts, clustering require a real trajectory-analysis
library (MDTraj or MDAnalysis). Neither is installed; installing into the
worker image is ~hundreds of MB and adds a heavy dependency.

Recommendation: ship A1+A2 first (pure Python + RDKit, already available),
then evaluate whether to add MDTraj as an optional "analysis worker" that runs
on demand rather than in the main simulation path. Keep analysis decoupled from
simulation so a failed analysis never fails a run.

### Phase A4 — export
Let users download `series.json` / `structure_series.json` and the derived
views so they can do deeper analysis in their own tools (MDTraj, VMD, etc.).
Already partially possible via artifact downloads; document it.

## Risks

- Computing per-frame RMSD on a 50-frame, 18k-solute-atom trajectory is cheap
  (~seconds). RMSF over all frames needs all frames in memory — gate behind a
  flag and cap frame count.
- Trajectory views are already solute-focused (solvent removed), so structural
  metrics computed on the view are meaningful and small.
- Do not block simulation completion on analysis: run analysis as a
  post-finalize step and report it as a separate artifact; failure leaves the
  run `completed`.
