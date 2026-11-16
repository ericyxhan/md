# Roadmap — beyond vanilla molecular dynamics

Companion to `docs/platform-vision.md`. Classifies capabilities into
**Tools** (unit operations) and **Experiments** (orchestration), per the
platform vision.

## Tier 1 — high value, tractable on OpenMM, builds on what exists

### 1.1 Steered MD (SMD) — Tool
Pull a ligand out of a pocket, force unfold a protein, compute work/PMF.
OpenMM: add a moving harmonic restraint. Low effort. New job param:
`steered_md: { atom_selection, direction, velocity_nm_ps, spring_k }`.

### 1.2 Metadynamics (well-tempered) — Tool/Experiment
Free-energy surfaces along collective variables. Via `openmm-plumed`.
Medium effort. New stage kind `metadynamics` with CV definitions.

### 1.3 Binding free energy — Experiment
- **MM-PBSA/GBSA** (cheaper, first): post-process trajectories with
  `gmx_MMPBSA`-style or a Python MMPBSA implementation. New analysis
  artifact + chart.
- **FEP/TI** (harder, killer feature): alchemical via `openmmtools`.
  New job type `fep` with lambda windows, BAR/MBAR analysis.

### 1.4 ML potentials (MACE/ANI) — Tool
Optional force field in the wizard. OpenMM-ML. Medium-High effort (model
bundling, GPU memory).

### 1.5 Constant-pH MD — Tool
Dynamic protonation during simulation. OpenMM ConstantPHMD. Medium effort.
Distinct from the existing static pH preparation.

### 1.6 Constant-pH preparation (done)
Static protonation at a given pH already exists via `ParameterizationSpec.ph`
(default 7.4, range 0-14) and PDBFixer (`strip_existing_hydrogens` rebuilds
from the templates and pH). Exposed in the MD wizard's System step. No
further work needed for *preparation*; the open item is dynamic
constant-pH *simulation* (1.5).

## Tier 2 — medium effort, big differentiators

### 2.1 Replica exchange (REST2) — Experiment
Multi-replica sampling. OpenMM `ReplicaExchange`. Needs multi-GPU or
sequential swaps on one GPU (slower).

### 2.2 QM/MM — Tool
QM region in the active site. OpenMM QMMM + ASE/Psi4. High effort.

### 2.3 Membrane properties analysis — Tool
Area per lipid, thickness, order parameters, density profiles. Natural
extension of membrane embedding. MDTraj + custom.

### 2.4 Mixed-lipid membranes — Tool (done)
Membrane prep now accepts an optional `lipid_composition` string in
packmol-memgen syntax (e.g. `POPC:POPE` or `POPC:POPE//DPPC`), overriding
the single `lipid` field. Exposed in the Membrane embedding UI as an
advanced text field.

### 2.5 Batch screening pipeline — Experiment
Dock + simulate many ligands, rank by binding. Fits Pipelines (fan-out).

### 2.6 Nucleic acids, carbohydrates, glycoproteins — Tool
Parameterization support: amber14/DNA.OL15, GLYCAM. prepare_system.py
needs biomolecule-type dispatch (BiomoleculeType already in schema).

## Tier 3 — large, strategic

### 3.1 Coarse-grained (Martini) — Tool
CG topologies + Martini FF. New preparation path. Large effort.

### 3.2 Adaptive sampling + MSMs — Experiment
Many short runs + analysis + spawning. Kinetics.

### 3.3 Multi-GPU / cloud bursting — Infrastructure

### 3.4 Collaboration (sharing, comments, reports) — already in Phase 4 of frontend plan.

## Feasibility notes (OpenMM stack)

- OpenMM supports PLUMED, replica exchange, ConstantPHMD, AMOEBA, QMMM,
  and OpenMM-ML. Most Tier 1/2 items are plugins, not new engines.
- ReaxFF would require LAMMPS — out of scope unless reactive chemistry
  becomes a priority.
- FEP/TI is the single highest-leverage item for drug design and composes
  with existing docking + simulation.

## Recommended next implementation order

1. Constant-pH preparation completion (expose pH in prep UIs) — small.
2. Mixed-lipid membranes — small, high value.
3. Steered MD — small, unlocks new experiment types.
4. Metadynamics via PLUMED.
5. MM-PBSA/GBSA binding free energy.
6. ML potentials (MACE).
7. Constant-pH MD.
8. Nucleic acids / glycoproteins.
9. Replica exchange.
10. QM/MM.
11. Coarse-grained (Martini).
