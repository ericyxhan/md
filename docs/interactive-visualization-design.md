# Lattice — interactive visualization design

This document extends `docs/frontend-design.md`. The shipped console is
functional but *documentary*: forms collect a request, text feeds report
progress, and results are rows in an artifact table with download buttons. The
user never sees the molecule they are about to simulate, cannot correct a
structure before spending GPU hours on it, and cannot play back what the GPU
produced. The v1 design deliberately listed "a molecule viewer, trajectory
player, or plotting suite" as a non-goal; this plan retires that non-goal and
turns the console into an end-to-end, visual platform:

> upload → **see and edit the structure** → **watch the system being built** →
> **monitor the run with live charts** → **inspect checkpoints** →
> **play the trajectory** → download for serious analysis.

Everything below is grounded in what the service already produces. The
simulation engine already writes every file we need; the gap is a thin
derived-artifact layer plus a viewer in the SPA.

## 1. What we already have to build on

A real run of the 7YAE workflow (present in `outputs/`) is the reference. The
numbers matter because they drive the design:

| Item | Real size | What it is |
| --- | --- | --- |
| `7YAE.pdb` (raw upload) | 0.8 MB, 9,031 atoms | small; renderable as-is |
| `outputs/metadata/prepared.pdb` | 32 MB, **398,753 atoms** | solvated box; 379,969 waters, ~18,800 solute atoms |
| `outputs/stages/production/trajectory.dcd` | **239 MB**, ~50 frames | 4.8 MB per frame at full atom count |
| `outputs/stages/production/checkpoint.chk` | 46 MB | OpenMM-internal binary; not renderable |
| `outputs/stages/production/state.xml` | 65 MB | portable OpenMM state |
| `outputs/stages/production/simulation.log` | ~7 KB CSV | `StateDataReporter` output: step, time, PE, KE, temperature, volume, density, speed |
| `outputs/stages/production/stage.json` | manifest | final energies, timings, steps, integrator snapshot |
| `progress.json` + SSE | live | phase/stage/step/percent already streamed to the browser |

Existing plumbing we can reuse without redesign:

- **Artifact kinds** (`service/api/app/services/artifacts.py`,
  `service/worker/reconcile.py`): `config`, `log`, `state`, `checkpoint`,
  `trajectory`, `structure`, `metadata` — closed sets, easy to extend.
- **Prep system** (`/api/v1/prep/system-prep`): already executes
  `remove_ligand`, `select_chain`, `add_ligand` on an uploaded structure and
  registers the result as a `FileRecord` usable as `complex_file_id`. The
  backend for "click to remove" already exists; only the visual layer is
  missing.
- **`inspect_pdb`** in `service/worker/prep_ops.py` (gemmi-based) and the
  unused `PDBInspection` type in `src/lib/types.ts`: the start of a structure
  inspection endpoint.
- **Worker image** builds `FROM openmm-cuda12:8.6.1` — it can gain `mdtraj`
  for trajectory slicing without a new base image.
- **SSE stream** (`/api/v1/jobs/{id}/events/stream`) with `job`, `progress`,
  `end` events — the transport a live "watch the run" view can ride on.
- **Capabilities endpoint** is already the source of truth for feature flags;
  the UI can degrade gracefully when the worker lacks view support.

## 2. Design principles for the visual layer

1. **Never ship the whole box.** Solvated systems are ~400k atoms and
   trajectories are hundreds of MB. The browser gets *derived views*:
   solute-focused, frame-capped, byte-budgeted. Raw artifacts stay
   download-only.
2. **Derived, never duplicated.** Views are computed from the canonical
   artifacts and cached next to them (`outputs/views/…`). The DCD the user
   downloads and the DCD the browser plays are different files, both derived
   from the same source of truth.
3. **The molecule is the hero.** Every screen where a structure exists shows
   it: wizard steps, prep jobs, job detail, results.
4. **Selection is a first-class action.** Click and drag to select
   residues/ligands/chains; selection drives removal, inspection, and
   analysis — mapped onto the prep operations the API already runs.
5. **Degrade, don't break.** No WebGL, huge structure, or missing view → the
   current text/table UI remains as the fallback. Visual features advertise
   themselves through `/capabilities`.
6. **Keep the calm console.** The viewer is embedded in the existing design
   system (cards, teal accent, restrained motion), not a bolted-on
   third-party-looking island.

## 3. Viewer and charting stack

### 3.1 Molecular viewer: Mol*

**Decision: Mol\*** (`molstar` npm package), embedded per route, code-split.

Rationale:

- **DCD support is built in** — `CoordinatesFromDcd` transform and
  `Viewer.loadTrajectory({ model: { kind: 'topology-url', format: 'pdb' },
  coordinates: { kind: 'coordinates-url', format: 'dcd', isBinary: true } })`.
  No custom binary parsing to own.
- **Trajectory playback UI is built in** — play/pause, frame scrubber,
  interpolation (`PluginConfig.Viewport.ShowTrajectoryControls` /
  `ShowAnimation`).
- **Selection mode is built in** — click atoms/residues, shift-click ranges,
  drag-box selection in the viewport; selections surface in a sequence panel.
  This is exactly the "click and drag to select things" interaction.
- **Maintained and standard** — RCSB retired NGL in favour of Mol\*; active
  fixes through 2025; TypeScript-native; embeds in React via
  `createPluginUI` + `renderReact18`.
- **Scales** — designed for million-atom models, so a capped 20k-atom view is
  trivial.

Trade-offs and mitigations:

- Bundle size (~1.5–3 MB gzipped) → load via `React.lazy` + Vite dynamic
  import inside a single `StructureViewport` wrapper component; the main
  bundle never imports molstar statically.
- Its full plugin UI is busy → configure a minimal layout (no left panel, no
  log) and drive it from our own toolbar, so it reads as part of Lattice.

**Rejected alternatives** (kept here for the record):

- **NGL** — smaller, delightfully simple API, real `TrajectoryPlayer`, PSF+DCD
  demo heritage. Rejected as primary because RCSB deprecated it and
  maintenance is minimal; revisit only if Mol\* bundle cost proves blocking.
- **3Dmol.js** — simplest embedding and click callbacks, but no DCD parsing
  and weaker large-structure performance. Viable only for a structure-only
  preview; not worth a second 3D dependency.

### 3.2 Charts: Recharts 3 (+ downsampling contract)

`simulation.log` rows are small (one CSV line per report interval, hundreds to
a few thousand per stage), so Recharts 3 (React 19-compatible) with the
existing design tokens is adequate, and it themes cleanly with Tailwind. The
series endpoints return at most ~2,000 downsampled points by contract, so
client performance is bounded. If frame counts grow two orders of magnitude,
swap the plot internals for uPlot behind the same `<ChartCard>` component —
do not couple pages to the chart library.

## 4. Derived views (the server-side contract)

The worker computes views at stage completion, next to the artifacts it
already reconciles. Layout inside the job workspace:

```text
outputs/
  views/
    prepared/           view of the built system (post-parameterization)
      view.pdb          solute + optional shells, capped atoms
      components.json   water/ions count, box vectors, composition summary
    production/         one directory per stage, once it has a trajectory
      view.pdb          topology paired 1:1 with view.dcd atom order
      view.dcd          strided, solute-focused trajectory (byte-budgeted)
      frames.json       frame_count, stride, dt_ps, atom_count, selections
      final.pdb         snapshot of the last frame (also used by live peek)
    analysis/
      series.json       parsed simulation.log columns for charting
```

Rules (enforced in the worker, documented in `frames.json`):

- **Atom budget**: strip solvent and ions by default; keep protein, ligands,
  membrane (if any), and optionally a configurable first water shell. Cap at
  ~25k atoms. For 7YAE this is ~18.8k atoms — 225 KB per DCD frame.
- **Frame budget**: stride so the DCD stays ≤ ~15 MB and ≤ 240 frames
  (~4 s at 60 fps). The 7YAE production stage (~50 frames × 4.8 MB) becomes
  ~50 × 225 KB ≈ 11 MB — fine. A 1 µs run with 5,000 frames strides to every
  20th frame.
- **Topology pairing**: `view.pdb` and `view.dcd` must be produced by the same
  `mdtraj.atom_slice(indices)` call so atom order matches exactly. DCD has no
  atom names; a mismatched pair is corrupt-by-construction.
- **Caching**: views are written once per (stage, fingerprint) and skipped if
  already present and the source artifact mtime/size is unchanged. Re-runs
  (retry `restart_stage`) regenerate views for that stage.
- **Kinds**: register views with a new artifact kind `view` (add to
  `ARTIFACT_KINDS` in both `reconcile.py` and `artifacts.py`, plus the
  schemas). The artifact table can then filter them out of the default list
  and the viewer fetches them by kind.

Tooling: `mdtraj` in the worker image (`pip install mdtraj` on the
openmm-cuda12 base). `traj = mdtraj.load('trajectory.dcd', top='…prepared.pdb')`
→ `atom_slice` → stride → `save_dcd`/`save_pdb`. Energy parsing is plain CSV
parsing of `simulation.log`.

## 5. New and extended API endpoints

All under `/api/v1`, same owner/session/CSRF model, all read-only except where
noted. Types mirrored in `src/lib/types.ts` per project convention.

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/files/{file_id}/inspect` | GET | Structure summary for any upload: chains, residue ranges, components (protein / water / ion / ligand with counts and residue names), atom count, model count, bounding box. Powers wizard and editor pickers. |
| `/files/{file_id}/preview` | GET | Raw upload served **inline** (correct `chemical/…` content type, `nosniff`) for direct rendering of small structures; large files return 409 with a hint to use the derived view instead. |
| `/jobs/{id}/views` | GET | Inventory of available views: prepared, per-stage, analysis; with `view.pdb`/`view.dcd`/`frames.json` URLs (signed by artifact ID, same path confinement as artifacts). |
| `/jobs/{id}/views/{view}/files/{name}` | GET | Inline, range-capable file serving for view assets (PDB/DCD/JSON). Reuses `artifact_path` confinement and `X-Content-Type-Options: nosniff`. |
| `/jobs/{id}/analysis/series` | GET | Chart-ready series from `simulation.log` (columns selectable, server-downsampled to ≤ 2,000 points, min/max preserved). |
| `/jobs/{id}/views/live` | GET | **Phase 4** — latest frame of the growing DCD extracted server-side (mdtraj stream-read of the final complete frame; truncated tails rejected). Polled every ~5 s while a stage is running. |
| `/jobs` (create) | POST | **Phase 2** — optional `structure_edits` block applied to the input before parameterization (see §6.3). |
| `/capabilities` | GET | New flags: `views.enabled`, `views.max_view_atoms`, `views.max_frames`, `analysis.series.enabled` so the SPA degrades gracefully on older workers. |

Notes:

- **Inline serving**: artifacts are currently `attachment`-only. View files
  are new, API-generated, content-typed (`chemical/x-pdb`,
  `application/json`), never user-supplied text rendered as HTML — plus
  `nosniff`, this stays inside the CSP threat model. Raw *uploads* previewed
  inline must be served with a non-HTML content type only.
- **Ownership**: every view route resolves through the existing
  `get_owned_job` / artifact-row indirection — the API never takes a
  filesystem path from the client, preserving the current security posture.

## 6. UX design per surface

### 6.1 New-simulation wizard — see and edit the system

Today `StepStructure` is a dropzone plus a ligand list. It becomes:

1. **Structure step (after upload)** — the uploaded complex renders
   immediately in a `StructureViewport` card beside the dropzone (raw file is
   small; ~9k atoms for 7YAE). Protein cartoon, ligands ball-and-stick,
   waters/ions toggled off by default with counts in the legend. The
   `/inspect` summary shows chains, ligands, cofactors, missing-residue
   warnings as chips. A PDB-ID download renders once fetched.
2. **Interacting with selection** — Mol\* selection mode (click residues,
   shift-click stretches, drag-box). The selection resolves to a readable
   list: *chain A, residues 45–52 · 8 residues · 126 atoms*. Buttons appear
   next to the selection: **Remove from system**, **Keep only this chain**,
   **Cancel**.
3. **Edits as a stack** — every removal/addition appends a step to an
   edit-stack panel (`Remove ligand CLR-401`, `Keep chain A`, `Add ligand
   CLR-402.sdf`), mirroring the existing prep operations. The viewport shows
   the *resulting* system live (client-side filtering for immediate feedback;
   authoritative filtering server-side on submit). Each step has an undo.
4. **System step** — parameterization defaults stay, but gain a live
   "what will be built" caption: bounding box, expected solvent count,
   ion count computed from pH/ionic strength where cheap to estimate.
5. **Review step** — final composition summary (atoms, chains, ligands,
   edits applied) beside the final structure view. Validation unchanged.

**Add** in the wizard means: upload additional ligands (existing dropzone →
`add_ligand`), and the parameterization controls already add waters/ions —
surface what they do in text and, later, in the prep preview.

### 6.2 The system-prep workspace — the visual builder

`SystemPrepPage` already does remove-ligand / keep-chain / add-ligand as
forms over a queue. It converges with the wizard editor:

- Upload (or pick a past upload) → 3D view + component inventory.
- Select-and-remove driven by clicks instead of residue-name text fields
  (text entry remains as an expert shortcut).
- Prep job runs (existing queue, progress, logs) and the page now *renders
  the output structure* on completion instead of only listing file IDs —
  the "visualize systems as they're being built" moment.
- "Use in simulation" deep-links to the wizard with the file preselected
  (already implemented — keep).

### 6.3 Where edits execute (backend)

Two supported paths, in order of preference:

1. **v1 (no API change): wizard edits → `/prep/system-prep`.** The visual
   editor's edit stack is exactly a `SystemPrepRequest.steps` payload. On
   submit, the wizard queues the prep job, waits for the output file (same
   polling the prep page uses), then creates the MD job with that
   `complex_file_id`. Zero backend work; one extra prep job; the user sees a
   "preparing your structure" step in the wizard's review.
2. **v2 (unified): `JobCreate.structure_edits`.** The edits ride along with
   the job; the worker applies them as a pre-parameterization filter step
   (`prep_ops` functions run in the job workspace before
   `prepare_system`), writing `inputs/edited.pdb` into the bundle. The edit
   stack appears in the job's events and config for reproducibility.

To support arbitrary click-drag selections (not just whole residue names or
chains), extend `prep_ops` with:

- `remove_residues` — explicit `[{chain, resnum, icode}]` list (gemmi deletes
  residues directly);
- `keep_selection` — the inverse, for "keep only what I selected".

These are small, testable, pure-structure operations in the existing style.

### 6.4 Job detail — monitoring becomes visual

The job page gains a **Structure** tab and a right-rail stage visual, keeping
every existing tab:

- **While queued**: nothing new.
- **While parameterizing**: the input structure remains rendered with a
  caption; when `metadata/prepared.pdb` appears, the view cross-fades to the
  **built system** (solute view + water/ion counts from `components.json`)
  with a "system built · 398,753 atoms · 379,969 waters" caption. This is the
  "watch the system being built" payoff and needs no live plumbing — the view
  appears when the artifact does.
- **While simulating**: the **Analysis** tab shows live charts from
  `progress.json` (percent, step) plus, per completed stage, the series from
  `analysis/series.json` — temperature, density, potential energy vs. step.
  The stage timeline gains per-stage snapshots (`final.pdb`) as thumbnails.
- **Terminal**: the **Trajectory** sub-view lists each stage with a frame
  count and a play button. Pressing play loads `view.pdb` + `view.dcd` via
  Mol\*'s trajectory preset — scrubber, playback speed, loop, and
  interpolation. Full trajectories remain downloadable from Artifacts.

**Checkpoint inspector** (uses data that already exists): each stage with a
`checkpoint.chk` gets a "Checkpoint" chip in the stage timeline opening a
small panel — step, time, final potential energy (from `stage.json`),
snapshot render (`final.pdb`), and the **Resume here** action, which maps
directly onto the existing retry modes (`resume`, `restart_stage`). The `.chk`
itself stays download-only; it is OpenMM-internal and never rendered.

### 6.5 Live peek (phase 4, deliberately last)

During a running stage, poll `views/live` (~5 s) to move the *view* structure
to the latest complete frame — the solute wiggles while the run proceeds.
Guardrails: solute-only atoms (≈225 KB per frame), poll only while the
Analysis/Structure tab is visible (pause on tab blur), and show "live peek"
as clearly distinct from a finished trajectory. If DCD tail reads prove
fragile, fall back to a slower `state.xml`-derived snapshot cadence.

## 7. Frontend architecture

```text
src/
  components/viewer/
    StructureViewport.tsx   # the only file importing molstar (React.lazy)
    useStructureView.ts     # load/preset/selection hooks; jsdom-mockable
    ViewerToolbar.tsx       # our controls: style presets, toggles, snapshot
    TrajectoryPlayer.tsx    # play/pause/scrub/speed UI over molstar controls
    SelectionPanel.tsx      # resolves selection → readable groups → edits
  components/charts/
    ChartCard.tsx           # recharts wrapper honoring design tokens
    SeriesChart.tsx         # energy/temperature/density plots
  pages/new-job/…           # wizard steps grow viewer cards
  pages/prep/…              # system-prep converges on the editor
  pages/JobDetailPage.tsx   # Structure + Analysis tabs, stage snapshots
```

- **One lazy boundary**: `StructureViewport` is dynamically imported; viewer
  routes preload on hover of a "View structure" affordance so the first paint
  is instant and the heavy chunk never blocks login/dashboard.
- **Queries**: new keys `["file", id, "inspect"]`, `["job", id, "views"]`,
  `["job", id, "series", stage]`; views poll only while a job is active
  (`refetchInterval` matches the existing adaptive pattern).
- **Testing**: jsdom has no WebGL — `useStructureView` is mocked in tests
  (the seam already used by `MembraneEmbedPage.test.tsx`); selection-to-edit
  mapping, series downsampling, and edit-stack logic are pure functions and
  tested directly.
- **Accessibility**: playback controls are real buttons with labels and
  keyboard support; every visual card carries its textual summary (atom
  counts, composition) so nothing is color-or-3D-only; viewer canvas gets an
  `aria-label` and the textual alternates live in the DOM.

## 8. Security review

- View assets are API-generated, content-typed, and `nosniff`; never served
  from user-controlled paths — resolved via artifact rows and the existing
  `storage.job_path` confinement.
- Inline raw-upload preview is restricted to chemical/text content types and
  refuse-lists `.html`-ish suffixes at the storage layer (already allowlisted
  by suffix at upload).
- No new auth surface: same session cookie, same CSRF posture (all new routes
  are GET; the wizard's prep/queue calls reuse existing POST routes).
- CSP: Mol\* needs `worker-src 'self' blob` and WebGL; no `unsafe-eval`
  required — verify against the nginx header baseline in the compose stack.
- Byte budgets are enforced server-side; the client cannot request an
  unbounded view (stride/atom caps are worker settings, advertised via
  capabilities).

## 9. Implementation phases

### Phase V1 — "See the system" (viewer foundation) — DONE

- Worker derives `outputs/views/prepared/{view.pdb,components.json}` using pure
  stdlib PDB parsing (strips waters/ions, caps at 25k atoms, caches by
  source size/mtime); `mdtraj` deferred to V3 trajectory slicing.
- `ARTIFACT_KINDS` gains `view` (worker + API + schemas); `artifact_kind()` maps
  `outputs/views/**` → `"view"`.
- New route: `GET /jobs/{id}/views` (+ `views.enabled` / `views.max_view_atoms`
  capability); new `GET /files/{id}/preview` inline upload route guarded by
  `max_preview_bytes`.
- SPA: `StructureViewport` (lazy Mol* chunk, minimal layout), job detail
  **Structure** tab with composition caption from `components.json`, wizard
  renders uploaded structures directly via `/files/{id}/preview`.
- Exit criteria: open any completed job → see the built system; open the
  wizard → see your upload.

### Phase V2 — "Build interactively" — DONE (path 1, zero API change)

- `remove_residues` / `keep_selection` in `service/worker/prep_ops.py` (gemmi-based
  explicit residue operations, unit tested).
- `SystemPrepOperation` gains `remove_residues` and `keep_selection` (API schemas +
  frontend types, step validation).
- Prep worker (`prep_worker.py`) wired to execute the two new operations.
- `GET /files/{id}/inspect` endpoint (PDB-only structure summary: chains, residues,
  components, atom count, model count, bounding box) — backend + tests.
- SPA: `SelectionPanel` (chain/ligand chips → edit stack), `EditStack` (pending
  edits with remove/clear), `StepStructure` integrates inspect + preview + editor.
- Wizard: `StepStructure` lets user click a chain → "keep chain", click a ligand
  → "remove ligand"; on Continue the wizard queues `/prep/system-prep`, polls for
  completion, and uses the output file as the MD job's `complex_file_id`.
- Exit criteria: click a ligand → remove it → run the simulation, without typing
  a residue name.

### Phase V3 — "Watch and analyze" — COMPLETE

- Backend: `mdtraj` added to worker requirements; worker generates per-stage
  `outputs/views/<stage>/{view.pdb, view.dcd, frames.json, final.pdb}` using
  mdtraj atom_slice (solute-only, topology/frame paired 1:1, stride-budgeted
  at ≤240 frames / ≤15 MB DCD) and `outputs/analysis/series.json` from
  `simulation.log` (CSV parsed, downsampled to ≤2,000 points with min/max
  preserved). Caching by source (size, mtime) signature; best-effort.
- `ARTIFACT_KINDS` gains `analysis` (worker + API); `artifact_kind()` maps
  `outputs/analysis/**` → `"analysis"`.
- New route: `GET /jobs/{id}/analysis/series` returns `SeriesOut` (group,
  source/view point counts, columns, points) with column-name mapping to the
  schema fields.
- `schemas.py`: `SeriesPoint`, `SeriesOut` added.
- Frontend: Recharts 3 installed behind `ChartCard` + `SeriesChart` components;
  `useJobSeries` query hook + `getJobSeries` API client; `TrajectoryPlayer`
  (lazy Mol* chunk) loads view.pdb + view.dcd via `loadTrajectory` with
  built-in playback controls (play/pause, scrubber, speed, loop).
- Job detail page: new **Analysis** tab with temperature, density, potential
  energy, and box volume charts plus trajectory player when a stage trajectory
  view exists.
- Exit criteria: play the production trajectory in-browser; judge equilibration
  from density/temperature plots.

### Phase V4 — "Live and deep"

- `views/live` frame peek during runs; SSE `frame`-tick events to trigger
  polls economically.
- Optional deeper analysis as worker-generated `analysis/` views (RMSD,
  RMSF, ligand contacts) — same derivation pattern, same viewer.
- `JobCreate.structure_edits` unified path (path 2) once the wizard proves
  the edit model.
- Shareable viewer snapshots (Mol\* `.molj` state export) attached to job
  events.

## 10. Quality checklist (extends §15 of frontend-design.md)

- [x] `npm run typecheck` and `npm run build` pass; the molstar chunk is
    code-split (main bundle ~486 KB, viewer chunk isolated).
- [x] Every visual feature degrades on `views.enabled: false` to today's UI
    (Structure tab hidden, wizard preview skipped).
- [x] View files never exceed configured byte/atom budgets (worker test
    asserts the 25k cap and truncation flag).
- [x] `view.pdb`/`view.dcd` atom counts match (worker test asserts pairing)
    — V3 backend: both produced by the same `mdtraj.atom_slice` call.
- [x] Selections map onto prep operations correctly — V2 edit-stack work.
- [x] Playback controls keyboard-operable; textual summaries accompany
    every viewer — V3 trajectory player (frontend).
- [x] No secret, bearer token, or internal URL in the bundle; view files are
    fetched through the existing authenticated artifact route with `nosniff`.
- [x] A job with no trajectory shows the prepared view and no player — no
    dead ends (V1 only derives the prepared view).
