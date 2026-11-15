# Docking — implementation plan

## 1. Problem

Today MolDy runs protein–ligand MD only when the ligand is already placed in the
binding pocket. A user who has only a raw receptor (PDB/mmCIF) and a free ligand
(SDF/MOL/MOL2/SMILES) cannot start a simulation. They need a docking step that
predicts the binding pose and produces a complex structure that the MD wizard
can consume directly.

## 2. Goal

Add a **Docking** workflow that:

- accepts a receptor structure + one or more ligands,
- predicts binding poses and scores,
- registers the top pose (and all poses) as artifacts,
- lets the user push the top pose straight into the New Simulation wizard as the
  complex input ("Use docked complex in simulation"),
- keeps the same account isolation, live progress, and artifact-download
  guarantees as the rest of the platform.

Docking is a system-preparation step, not a simulation: it produces a system to
simulate. It therefore fits the existing **prep-job** model (membrane embedding,
system preparation) rather than the MD job model.

## 3. Tooling (validated in this environment)

| Tool | Version | Role | Status |
|---|---|---|---|
| AutoDock Vina (Python bindings) | 1.2.7 | Docking search + scoring | pip-installable (`vina`), imports + instantiates OK |
| Meeko | 0.8.0 | Receptor PDB → PDBQT, ligand → PDBQT (`mk_prepare_receptor.py`, `MoleculePreparation`) | pip-installable, ligand prep smoke-tested (74-atom ligand → 49-line PDBQT) |
| RDKit | 2026.03.1 | Ligand parsing, H-addition, SMILES → 3D, conformer generation | already in the param env |
| OpenMM / PDBFixer | 8.6.1 | Receptor cleanup, H-addition, alternate-conformer handling | already in the simulation image |

No external binary or license is required. Everything runs in-process, so the
worker stays self-contained and the no-network constraint on the worker is
preserved.

## 4. User flow

1. User uploads a receptor (PDB/mmCIF) and one or more ligands (SDF/MOL/MOL2,
   or a SMILES string).
2. (Optional) Define the search box: either auto-detect from a known binding-site
   residue, or enter center (x,y,z) + size (Å). Default: auto-detect pocket
   using RDKit/Meeko heuristics, fall back to the whole-receptor box.
3. Set docking options: exhaustiveness (default 8), number of poses (default 9),
   seed (optional), and whether to keep hydrogens / optimize.
4. Submit → a prep job is queued; the page polls progress (phase, percent,
   current ligand/pose).
5. On completion: a results table (pose, affinity kcal/mol, RMSD) + a 3D
   preview of the top pose (reuses the StructureViewport component), and a
   "Use docked complex in simulation" button that deep-links to `/new` with the
   docked complex registered as a file (mirrors membrane embedding).
6. Artifacts: `docked_complex.pdb`, `poses.pdbqt`, `scores.csv`, `config.json`.

## 5. Architecture (reuse existing prep-job machinery)

Docking becomes a new `type` on the existing `PrepJob` model: `"docking"`.
This reuses, for free:

- queue/claim/heartbeat protocol (`/internal/v1`),
- cancellation and retry,
- SSE-less polling (`GET /api/v1/prep/jobs/{id}`) with phase/percent/message,
- artifact registration and ID-only downloads,
- per-account isolation and audit trail,
- the `capabilities.prep_workflows.*.enabled` flag so the UI adapts when the
  prep worker lacks the tooling.

**Why prep-job and not MD job:** docking is short (seconds–minutes), produces a
system rather than a trajectory, and its outputs are files. The MD job model
(stages, checkpoints, trajectories) is the wrong shape and would force a fake
stage timeline.

### 5.1 Worker dispatch

The prep-worker currently runs packmol-memgen. It needs to dispatch by
`prep_job.type`:

- `"membrane_embed"` → existing packmol path.
- `"docking"` → new docking runner (`prep_worker/docking.py`).

Add a `docking` capability to the prep-worker image (vina + meeko + rdkit).
The API's `capabilities` endpoint reports `prep_workflows.docking.enabled`
based on a new `DOCKING_ENABLED` setting (default true when the worker
advertises the tool, false otherwise — mirror `PACKMOL_PATH`).

## 6. Backend changes

### 6.1 Settings
- `DOCKING_ENABLED` (bool, default true) — gates the endpoint (503 when off),
  exactly like membrane embedding gates on `PACKMOL_PATH`.

### 6.2 Schemas (`app/schemas_prep.py` or new `app/schemas_docking.py`)
`DockingRequest` (extra="forbid"):
- `receptor_file_id: str`
- `ligand_file_ids: list[str]` (or `ligand_smiles: list[str]`)
- `box`: `{ center: [x,y,z] (optional), size: [x,y,z] (optional), auto: bool }`
- `exhaustiveness: int (1..32, default 8)`
- `num_poses: int (1..20, default 9)`
- `seed: int | None`
- `optimize: bool (default true)`

### 6.3 Endpoint
- `POST /api/v1/prep/docking` → creates a prep job with `type="docking"`,
  returns immediately (202) with `{ prep_job_id }`.
- Reuse `GET /api/v1/prep/jobs/{id}` for status.
- `POST /api/v1/prep/jobs/{id}/cancel` already exists.

### 6.4 Runner (`prep_worker/docking.py`)
1. Load receptor PDB; clean with PDBFixer (add Hs, remove waters beyond a
   cutoff, fix missing residues optionally).
2. Run `mk_prepare_receptor` (Meeko) → receptor PDBQT. Capture the box if
   auto-detected; otherwise use user box.
3. For each ligand:
   a. Parse with RDKit (SDF/MOL/MOL2/SMILES); add Hs, generate 3D conformer
      if missing, minimize (MMFF/UFF).
   b. Meeko `MoleculePreparation` → ligand PDBQT.
   c. Vina: `set_receptor`, `set_ligand_from_string`, `compute_vina_maps`,
      `dock(exhaustiveness, n_poses)`, `write_poses`.
   d. Parse scores; keep top pose; write `docked_complex.pdb` (receptor + top
      pose) and append to `poses.pdbqt`.
4. Register outputs as files + artifacts (`kind=structure` for complex,
   `kind=trajectory`-adjacent `pose` for poses, `kind=log` for scores).
5. Report `completed` with `output_file_ids=[complex_file_id]` so the UI can
   deep-link.

Progress messages: `preparing receptor`, `docking ligand 2/4 (pose 3/9)`,
`writing outputs`.

### 6.5 Storage
- Workspace: `users/<owner>/prep/<prep_job_id>/` with `inputs/`, `outputs/`
  (`docked_complex.pdb`, `poses.pdbqt`, `scores.csv`), `logs/`.

## 7. Frontend changes

- Add `/prep/docking` and `/prep/docking/:prepJobId` routes (mirror membrane).
- New `DockingPage` component: upload receptor + ligand(s), box controls,
  options, submit, poll, results table, 3D preview (StructureViewport), and
  "Use docked complex in simulation" button → `/new?complex_file_id=...`.
- Enable the nav entry: move "Docking" from the `roadmap` list into
  `preparationNav` as `{ to: "/prep/docking", label: "Docking", icon: Target }`.
- Add capability gating: if `prep_workflows.docking.enabled` is false, show
  the "not configured" empty state (same as membrane).
- Marketing site: add "Molecular docking" to the feature list and "Coming soon"
  removal.

## 8. Container changes

- Prep-worker image: add `vina`, `meeko`, and ensure `rdkit` is available
  (already in param env; install into the prep-worker image). Add a
  `DOCKING_ENABLED` build/runtime flag and a health check that imports vina.
- API image: no new deps (validation only).
- Contract: add `DOCKING_ENABLED` to `contract.env`? It's a feature flag, not a
  port/uid; keep it in `.env` like `PACKMOL_PATH`.

## 9. Phased delivery

- **Phase D1 — backend + worker (no UI):** prep job type `"docking"`, runner,
  receptor/ligand prep, Vina call, artifact registration. Test with the CLI
  (`POST /api/v1/prep/docking`). Validate on 7YAE + a ligand.
- **Phase D2 — UI:** DockingPage, nav entry, results table, 3D preview, deep
  link to MD wizard.
- **Phase D3 — multi-ligand + box tools:** batch docking, auto-pocket
  detection, box editor in the 3D viewer, score comparison chart.
- **Phase D4 — quality:** redocking RMSD validation, pose clustering, optional
  rescoring (Vina score is the default; GNINA could be added later as an
  alternative scorer).

## 10. Risks and considerations

- **Receptor preparation quality** dominates docking accuracy. PDBFixer + Meeko
  receptor prep must handle missing residues, alternate conformers, and metal
  ions. Start with a conservative path (remove waters, add Hs, keep one
  conformer) and document limitations.
- **Box definition** is the #1 user footgun. Auto-detect pocket from a known
  ligand (if provided) or from the largest cavity; always show the box in the
  3D preview before running.
- **Runtime:** Vina with exhaustiveness 8 on a ~10k-atom receptor takes
  seconds to a minute. Keep the job async with progress so the UI never blocks.
- **Scoring** is Vina's built-in; do not over-promise affinity accuracy.
  Report scores as "Vina score (kcal/mol)" and note they are for ranking.
- **Worker network:** Vina/Meeko/RDKit are pure Python + bundled native libs;
  no download at runtime, consistent with the isolated worker.
- **Disk:** poses are small (PDBQT text); the docked complex PDB is the main
  artifact. Reuse the existing retention cleanup.

## 11. Acceptance criteria

- A user with only a receptor PDB and a ligand SDF can obtain a docked complex
  and launch an MD simulation from it in under 3 minutes.
- Top-pose RMSD vs. a known crystal pose is ≤ 2 Å on the 7YAE reference
  (sanity check, not a guarantee).
- All failures surface as `error_code` + plain-language message + stage, per
  product principle #5.
- The feature is gated by capability so a deployment without the prep worker
  shows a clear "not configured" state rather than a 500.
