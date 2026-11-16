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

## Tooling recommendation

| Tool | Verdict | Why |
|---|---|---|
| **MDTraj** | **Primary choice for A3** | Pure-Python + C extensions, reads DCD/PDB natively, first-class RMSD/RMSF/Rg/H-bonds/DSSP/contacts. ~100 MB. Clean API (`md.load`, `md.rmsd`, `md.compute_rg`). Best fit for our DCD + PDB-topology pipeline. |
| **MDAnalysis** | Optional, for advanced users | More powerful (atom selections, PCA, custom analysis) but heavier and a steeper API. Keep as an opt-in extra, not a core dep. |
| **RDKit** | Keep for small-molecule work | Great for ligand RMSD vs. crystal pose, torsions, conformer analysis. Already in the param env. Not a trajectory-analysis tool — don't use it for protein RMSD/Rg. |
| **PyTraj / cpptraj** | Skip | Amber-centric; pulls in AmberTools. We're OpenMM-based. |
| **OpenMM** | Already have it | Energy re-evaluation on frames is possible, but structural metrics are not its job. |

**Phased dependency strategy (keeps the worker image lean):**

- **A2 (lightweight, no new deps):** implement RMSD and Rg in pure Python using
  a minimal DCD reader + NumPy (already in the image). Enough for the 80% case
  and adds zero image weight.
- **A3 (heavy):** add MDTraj as an optional dependency of a separate
  `analysis-worker` (or an extra in the prep/sim image), invoked on demand.
  Never block simulation completion on it.

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

## Full catalog of trajectory analyses a lab user may want

Grouped by category. "Cost" = relative compute on a solute-focused view
(~18k atoms, 50 frames). "Lib" = recommended library.

### A. Thermodynamic / state (already have, from simulation.log)
- Temperature (K) — have
- Pressure / volume — have (volume)
- Potential, kinetic, total energy — have (PE, KE)
- Density — have
- Speed (ns/day), elapsed time — have (speed, elapsed_s)
- Step / time axis — have

### B. Global structure stability
- RMSD vs. starting frame (backbone / all-atom / ligand) — **A2**
- RMSD vs. reference (crystal) structure — A2 (needs reference upload)
- RMSD matrix / pairwise RMSD across frames — A3
- Radius of gyration (Rg) over time — **A2**
- End-to-end distance, asphericity, eccentricity — A3
- RMSF (per-residue Cα fluctuation) — A3 (needs all frames in memory)
- B-factor comparison (simulated vs. crystal) — A3

### C. Ligand-specific
- Ligand RMSD vs. docked/crystal pose — A2 (single-frame compare)
- Ligand RMSD vs. starting pose over time — A2
- Binding-site (pocket) RMSD — A2
- Ligand torsion angle time series — A3 (RDKit)
- Ligand-protein contacts over time — A3
- Ligand RMSF / atomic fluctuations — A3

### D. Interactions
- Hydrogen bonds: count over time, occupancy per donor-acceptor pair — A3 (MDTraj)
- Salt bridges / ionic contacts — A3
- Hydrophobic contacts — A3
- π-π / π-cation interactions — A3
- Water bridges — A3 (heavy)
- Contact map (residue-residue) — A3

### E. Protein structure
- Secondary structure (DSSP) time series — A3 (MDTraj)
- Secondary-structure content (% helix/sheet/coil) over time — A3
- Ramachandran (φ/ψ) distributions — A3
- Per-residue solvent-accessible surface area (SASA) — A3
- Solvent-accessible surface area (total) over time — A3

### F. Dynamics / advanced
- PCA / essential dynamics (eigenvectors, projections) — A3+ (MDAnalysis)
- Free-energy landscape (PCA-based) — A3+
- Clustering of frames (RMSD-based) — A3+
- Diffusion / MSD — A3+
- Autocorrelation of velocities — A3+

### G. Energetics (beyond state reporter)
- Interaction energy (protein-ligand) over time — A3 (re-evaluate with OpenMM)
- Per-residue energy decomposition — A3+ (heavy)

### H. Export / downstream
- Download series.json, structure_series.json
- Download derived views (PDB + DCD) — already
- Export to CSV for custom analysis — trivial addition
- Notebook-friendly (HDF5/NetCDF) — future

## Prioritized roadmap

1. **A2 (now):** RMSD (backbone + ligand) and Rg time series + charts.
   Cheap, high-value, no new deps.
2. **A3 (next):** RMSF, H-bond count/occupancy, secondary-structure
   content, SASA. Requires MDTraj in an on-demand analysis worker.
3. **A3 (later):** contact maps, clustering, PCA/free-energy landscape.
4. **A4:** export formats and documentation.

## Notes on scope

- Compute on the *solute view* (solvent removed) so metrics are meaningful and
  cheap; keep the full system available for download for users who need it.
- Cap frame counts for memory-heavy metrics (RMSF over all frames) and gate
  behind a flag.
- Analysis must never block or fail a simulation run; report as separate
  artifacts with their own status.
