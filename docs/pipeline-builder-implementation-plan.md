# Pipeline builder — implementation plan

## 1. Vision

A visual, Foundry-style pipeline builder where a user assembles a multi-step
MD workflow (prepare → (dock) → (embed) → simulate → analyze) on a canvas and
launches it in one place, instead of clicking through four separate tools and
tracking file IDs by hand. Nodes are MolDy operations; edges carry file IDs.

## 2. Phases

- **P0 — Linear stepper (ship first).** A vertical stepper of node cards.
  Each node is a MolDy operation with inline config. "Run pipeline" executes
  the steps in order, passing the output of step N into step N+1, polling each
  to completion. Client-side orchestration (tab must stay open). ~2 weeks.
- **P1 — React Flow canvas.** Swap the stepper for `@xyflow/react` (v12, MIT,
  already installed). Draggable nodes, typed edges (structure / complex /
  trajectory), fan-out (one receptor → N ligands) and fan-in. ~3–4 weeks.
- **P2 — Server-side execution engine.** Move orchestration to the API:
  `Pipeline` + `PipelineRun` models, topological sort, per-node status, retry
  from a node, cached upstream outputs. Tab can close. ~4 weeks.
- **P3 — Templates & sharing.** Save pipelines as templates, clone, share
  read-only links. ~2 weeks.

## 3. Node types (MolDy-native only)

| Node | Wraps | Input | Output |
|---|---|---|---|
| Upload | file upload | — | file_id |
| System Prep | `/prep/system-prep` | file_id | prepared PDB |
| Membrane Embed | `/prep/membrane` | file_id | embedded PDB + PSF |
| Docking | `/prep/docking` | receptor + ligand(s) | docked complex PDB |
| Simulation | `/jobs` (MD) | complex file_id | trajectory, states, logs |
| Analysis | views/series | job_id | charts (future) |

Edges are typed by file kind so the canvas rejects nonsensical connections.

## 4. Data model (P2)

- `pipelines`: id, owner_id, name, definition (JSON: nodes + edges + per-node
  config), created_at, updated_at.
- `pipeline_runs`: id, pipeline_id, owner_id, status, started_at, completed_at.
- `pipeline_run_nodes`: run_id, node_id, job_id (nullable), prep_job_id
  (nullable), status, started_at, completed_at, error.

Child jobs/prep jobs carry `pipeline_run_id` + `node_id` for provenance.

## 5. P0 implementation (client-side stepper)

- Route `/pipelines` (new) + nav entry "Pipelines".
- Keep existing "Workflows" (base systems) as "Base systems" to avoid
  confusion.
- Page: list of pipelines (localStorage for P0; server-side in P2), create
  new, open builder.
- Builder: vertical list of node cards. Each card: type selector, config form
  (reuse existing step components where possible), status badge, output preview.
  "Add step", "Remove", "Move up/down". "Run pipeline" iterates, calling the
  relevant API per node, polling to terminal, extracting output file id, feeding
  next node. Stop on failure.
- Reuse `FileDropzone`, `Field`, `ProgressBar`, `PrepJobRow` patterns.

## 6. Risks

- Scope creep into a general workflow engine. Guard by refusing arbitrary code
  nodes.
- Drag-and-drop UX on mobile. P0 stepper is the safety net.
- State sync between node config, edges, run status. Use `useReducer` + context
  (no new global state lib, consistent with codebase).
