# MolDy — Persona-based critique and review (whole software stack)

_Date: 2026-11-16 (recorded from current repo state)_

This review covers the full stack observed in the repository: the core OpenMM CLI pipeline (`prepare_system.py`, `simulate.py`, `config.py`, `stages.py`, `parameterization.py`, etc.), the FastAPI control plane and workers (`service/api`, `service/worker`), the React web console (`service/web`), the marketing site (`site/`), docs, Docker/Compose/Caddy setup, and related tooling/tests/docs present.

## Scope notes (what I inspected)
- Root docs: `README.md`, key `docs/*.md` (service implementation plan, platform vision, frontend review, pipeline/analysis/docking plans, roadmap).
- Service: `service/README.md`, API routers/services/schemas (sampled), worker code patterns, compose/Caddy.
- Web: `service/web/src` pages/components/lib (structure + representative pages: Dashboard, Jobs, JobDetail, NewJob, Pipelines, prep pages).
- Marketing: `site/` structure and content patterns (sampled).
- Tests: presence in `service/api/tests`, `service/web/src/test*` implied by files, root `tests/`.


## Executive summary
MolDy is a technically ambitious MD platform: a solid OpenMM CLI core plus a FastAPI control plane, GPU worker protocol, React web console, and growing product features (membranes, docking, pipelines, automatic analysis). The engineering direction is thoughtful (leases/fencing, internal/public API split, staged checkpoints), and the docs are unusually candid about limits (CUDA, removed/partial features). The main gaps are productization and trust for broader adoption: deployment/ops complexity, user-facing error remediation, missing “decision-grade” outputs for drug discovery (notably free-energy workflows), weak onboarding/presets, and engineering operational maturity (observability, secrets/rotation story, SQLite scaling posture, CI/CD/runbooks).

## Top 10 actions (prioritized)
1. **Ship a “golden path” onboarding**: in-app guided flow (upload → validate → run → interpret) + 2–3 presets (soluble protein+ligand, membrane protein) with a tiny example dataset.
2. **Turn failures into fixes**: classify common errors (PDBFixer/OpenFF/forcefield coverage, OOM, disk full, missing deps) with actionable messages, links, and “next steps” in Job Detail/logs.
3. **Publish a minimal deployment matrix + smoke test**: supported OS/GPU/CUDA/driver combos, a one-command deploy checklist, and an automated smoke test (create user → tiny job → artifacts).
4. **Define and document data/provenance policy**: retention, cleanup behavior, export bundle contents (spec, versions, seeds, artifacts) and a clear “run reproducibility” section in-product/docs.
5. **Strengthen scientific credibility for CADD users**: document validated use-cases, limitations per method, and a roadmap/guardrails for docking→MD→analysis (replicates guidance, when not to trust results).
6. **Improve queue/cost transparency**: show queue position context, resource requirements, and rough runtime guidance (even ranges) per preset/profile.
7. **Harden ops/security posture**: secrets management/rotation guidance, session/token best practices, dependency/image scanning, and a short threat-model note for self-hosted deployments.
8. **Add observability + runbooks**: metrics (queue depth, job latency, worker health, GPU/disk), structured event naming, alerting hooks, and runbooks for OOM storms, stuck leases, disk full.
9. **Tame frontend complexity**: progressive disclosure in New Job, consistent naming across prep/jobs/workflows/pipelines, glossary/tooltips for MD terms, and revisit large bundles (Molstar/code splitting) for load performance.
10. **Plan scaling path deliberately**: document SQLite limits and a migration path (e.g. Postgres) triggers, plus background job bounds/timeouts for heavy analysis to avoid worker instability.

---

## 1) Enthusiastic evangelist (bioinformatics/startup founder energy)

**What they love**
- Clear “from structure to trajectory to insight” story: prep → parameterization → staged equilibration/production → analysis/views is compelling and matches what wet-lab+comp teams ask for.
- Modern product shape: FastAPI + GPU worker + web UI + marketing site signals a real platform, not just scripts.
- Strong pragmatic choices: checkpointed stages with explicit `state.xml` semantics (and caveats about checkpoints tied to integrator/barostat) show depth; progress/manifest reconciliation is thoughtful.
- Differentiators already present: membrane embedding, docking flow, pipelines UI (stepper), automatic analysis artifacts, trajectory views — these move beyond “run a script.”
- Docs are unusually honest in places (version matrix, CUDA constraints, pitfalls), which builds trust.

**What they’d amplify**
- “One platform for prep, docking, membranes, MD, and analysis” — position against stitching together local tools.
- Emphasize reproducibility (immutable uploads, canonical specs, job history, artifacts).

**Risks they’d downplay but shouldn’t**
- Operational complexity (GPU node, Docker, Caddy/Tailscale, volumes, migrations) is real; evangelists must pair hype with a “day 1 install reality check.”

---

## 2) Pessimistic competitor (commercial MD SaaS / established vendor)

**Where MolDy looks vulnerable**
- Feature breadth is early: no FEP/REST at depth, no clear HPC scheduler story beyond a single GPU worker model, limited provenance/compliance language, no enterprise SSO/MFA/SCIM story visible.
- Trust & validation: scientific claims need benchmarks, regression tests across force fields/ligand chemistries, and clear uncertainty limits; “works on our cases” is not enough.
- Scalability: single-worker / simple queue model is fine for pilots but not obviously multi-tenant, multi-GPU, priority queues, cost accounting, or spot strategies.
- Supportability: many moving parts (param env, sim env, packmol-memgen, docking deps) increase support burden and failure modes.
- Lock-in narrative is weakly defended: users may ask “can I export everything and run elsewhere?” (partially addressed by artifacts/config, but not a first-class “exit kit”).

**Where MolDy is annoying (to a competitor)**
- Open-source-adjacent posture + clear technical depth in docs can attract academic labs quickly.
- Focused workflow UX (guided job creation, views, analysis charts) can feel faster than legacy portals.
- Rapid iteration visible in docs/plans suggests momentum.

**What they’d bet on**
- Target niche: small labs wanting GPU MD without cluster admin, plus membrane/docking-adjacent workflows — win there before chasing pharma-scale validation.

---

## 3) Somebody who hates this platform (“hostile” user/reviewer)

**Top frustrations (likely)**
- “Another stack to deploy”: Docker + host dirs + env vars + tokens + Tailscale/Caddy is intimidating for bench scientists; errors in setup feel opaque.
- Mixed UX languages: CLI-first heritage leaks into web (TOML concepts, stage names, raw file IDs) — power users tolerate it, others bounce.
- Failure UX: when prep/MD fails, users need actionable, ranked causes (missing atoms, forcefield coverage, disk space, GPU OOM) — generic logs are hostile.
- Performance opacity: no clear cost/time estimates before launch; long queues/gpu waits feel like a black hole.
- “Marketing promises vs reality”: if site implies turnkey science, but setup requires sysadmin work, backlash follows.
- Documentation sprawl: many markdown files are great internally but can overwhelm external users (which is canonical?).

**What would make them angrier**
- Silent data loss/cleanup behavior not obvious (retention/orphans mentioned in service README but UX/clarity matters).
- Account/password flows and security posture described in README may feel ad hoc without clear threat model docs.

---

## 4) UI/UX expert

**Strengths**
- Clear information architecture direction in docs (Workspace / Tools / Experiments) and a dedicated web app (`service/web`) rather than bolted-on forms.
- Good use of modern stack (React, routing, data fetching patterns implied) and component structure (`components/ui`, pages split).
- Pipelines page shows product thinking (saved locally, stepper orchestration) — good MVP for non-experts.
- Analysis surfaces (charts, views, RMSF mention in history/docs) are the right direction for “insight, not just output files.”

**Weaknesses / risks**
- **Cognitive load in New Job flow**: many advanced knobs (integrators, restraints, stages) risk overwhelming novices; needs progressive disclosure, presets, and “safe defaults” narrative.
- **Error presentation**: job detail/logs must turn raw stderr into guided remediation (links to docs, “did you mean…”, common fixes). “Logs tail” is necessary but not sufficient.
- **Navigation clarity**: with prep subpages, pipelines, workflows, jobs — ensure consistent naming vs backend concepts (prep job vs simulation job vs workflow).
- **Accessibility & responsiveness**: not verified here, but data-dense tables/charts need keyboard support, contrast checks, and mobile degradation strategy.
- **Onboarding gap**: no obvious in-app guided tour for first run (upload → validate → run → interpret analysis).
- **Design system drift risk**: many pages suggests need for shared patterns (empty states, status pills, long-running job affordances) — `docs/frontend-review.md` is a good sign but must stay enforced.

**High-impact UX recommendations**
- “Run readiness” checklist before submit (files valid, disk ok, estimated resources unknown → at least warn).
- First-class “explain this result” tooltips for RMSD/Rg/H-bonds/DSSP/SASA outputs.
- Make pipelines the default path for common recipes; hide power-user JSON/TOML mental model unless requested.

---

## 5) Drug discovery researcher (medicinal chemist / CADD scientist)

**What’s promising**
- Docking integration (AutoDock Vina path documented) plus MD is a valuable combo if the handoff is smooth (poses → system prep → MD).
- Membrane embedding matters for membrane targets; lipid composition support is increasingly important.
- Automatic trajectory analysis (RMSD, Rg, H-bonds, DSSP, SASA, RMSF noted) covers common stability/readout needs.
- Support for protein+ligand inputs and parameterization workflow is aligned with real projects.

**Gaps / concerns**
- **Binding affinity story is incomplete**: MM-PBSA/GBSA/FEP are the big asks; current stack does not deliver trustworthy end-to-end free energy (and you removed a half-baked attempt — wise, but the gap remains).
- **Ligand & chemistry coverage**: covalents, metals, unusual cofactors, tautomer/protonation control at scale, and charge assignment transparency need clear limits and validation.
- **Ensemble & sampling**: single trajectories are weak evidence; need guidance on replicates, enhanced sampling roadmap (aMD/metadynamics/REST) or integrations.
- **Nucleic acids, glycans, glycoproteins**: explicitly called out as future in roadmap — blocks many targets today.
- **Reproducibility for publications**: need exportable provenance (software versions, forcefield files/versions, random seeds, exact commands/specs) in a citable bundle.
- **Docking quality**: Vina is a starting point; users will ask about rescoring, constraints, covalent docking, induced fit — manage expectations.

**What would win them**
- “Validated protocol” presets (e.g. soluble protein+ligand, GPCR in membrane) with known test systems and expected ranges.
- Clear guidance: when MD is informative vs misleading for this platform’s current methods.

---

## 6) Lab user (experimentalist / graduate student running simulations occasionally)

**What helps**
- Web UI lowers the barrier vs only CLI.
- Guided flows (new job, prep pages) are the right direction.
- Seeing job status, logs, artifacts in one place reduces “SSH + grep” pain.

**Pain points**
- **Setup burden**: getting a GPU box, Docker, permissions, storage paths right is a project by itself.
- **Concept overload**: “stages”, “equilibration blocks”, “parameterization env”, “views vs artifacts” — needs plain language.
- **Waiting & uncertainty**: no clear ETA, queue position visibility helps but not enough without resource explanation.
- **Debugging is scary**: long logs, stack traces, and OpenMM/PDBFixer errors are not lab-user friendly.
- **Data management**: where results live, how long kept, how to share with PI/collaborators — unclear without policy docs in-product.

**What they need most**
- “Happy path” templates: upload protein+ligand → run standard equil+short prod → download key plots and a summary PDF/HTML report.
- In-app glossary/tooltips for MD terms.
- One-click “share read-only link to this job” (if multi-user/org model evolves).

---

## 7) Senior software engineer (platform/backend/infrastructure)

**Architecture observations (positives)**
- Separation of concerns: CLI core reused concepts; service layer adds API, queueing, worker protocol, artifacts — reasonable evolution.
- Internal vs public API separation (Caddy hiding `/internal/*`) is good security hygiene.
- Use of SQLite with pragmas and Alembic is pragmatic for early stage; job token fencing, leases, reaper show attention to distributed-worker failure modes.
- Worker isolation ideas (separate prep worker, fixed commands, process groups) are appropriate.
- Tests mentioned (API/worker/web) and `docs/frontend-review.md` show maturity signals.

**Concerns / risks**
- **SQLite at scale/concurrency**: fine for small deployments, but write contention, backup/restore operational load, and “single writer” limits will bite with many users/jobs; plan migration path (Postgres) or clearly document limits.
- **Secrets & auth**: bearer tokens, worker tokens, session secrets in env — operationally easy but error-prone; need rotation story, secret management guidance, and audit of defaults.
- **Observability**: structured logs mentioned; missing visible story for metrics (queue depth, job durations, GPU utilization), tracing, alerting.
- **Idempotency & retries**: worker protocol has leases/fencing (good), but end-to-end idempotency for uploads/starts/retries should be explicit and tested.
- **Container/security hardening**: read-only FS, cap drops noted in compose snippets in README — good; ensure all images follow least privilege, pin bases, scan dependencies (OpenMM/conda wheels are heavy).
- **Dependency hell risk**: multiple Python envs (param, sim, worker, api) + system deps (packmol) — reproducible builds and version pinning are critical; Docker helps but images are large and fragile.
- **API contract discipline**: Pydantic with `extra="forbid"` is good; need versioning strategy for `/api/v1` and job spec evolution.
- **Data layout & paths**: per-user dirs under DATA_ROOT is good isolation intent; must be vigilant about path traversal, symlinks, and cleanup races.
- **Frontend build size**: Molstar chunk warnings in builds — acceptable short-term but watch load performance; consider code splitting/lazy routes.
- **CI/CD not described here**: no obvious pipeline docs in inspected files — needed for confidence (lint, test, image builds, migration checks).

**Suggestions**
- Document SLOs and operational runbooks (incident: GPU OOM storm, disk full, stuck leases).
- Add a “minimal supported deployment” matrix and automated smoke test (deploy → create user → run tiny job).
- Introduce background job for heavy postprocessing consistently (and timeouts/resource limits) — MM-GBSA attempt showed complexity; analysis should be bounded.

---

## Cross-cutting themes (synthesis)
1. **Strong technical core, productizing in progress**: the simulation/worker plumbing is thoughtful; UX and “science guarantees” are the main gaps to a broad audience.
2. **Honesty in docs is an asset**: keep it (limits, CUDA notes, removed features) — it differentiates from overpromising tools.
3. **Biggest user-facing risks**: deployment complexity, error interpretability, and missing “decision-grade” outputs (free energy, validated protocols) for drug discovery.
4. **Biggest engineering risks**: operational scale (SQLite, GPUs, multi-env dependencies), observability, and long-term API/spec evolution.
5. **Fastest wins**: better failure messages + presets + onboarding; a published “known good” example library; clearer export/provenance bundle.


---

## Addressing hostile-user / high-friction concerns (concrete actions)

### 1) Deployment complexity (“another stack to deploy”)
**Pain:** Docker + host dirs + env vars + tokens + Caddy/Tailscale feels opaque and error-prone for non-sysadmins.

**Concrete actions**
- Publish a **single “deploy in 30 minutes” path** (one page): required host (Ubuntu version, NVIDIA driver/CUDA compatibility), disk layout, exact commands, expected outputs.
- Add a **`make deploy-check` / script** that validates: Docker + Compose versions, GPU visibility, required env vars present, writable data dirs/permissions, ports free, and runs a minimal health check.
- Provide **two deployment tiers** in docs: (a) *Lab server (recommended)* with Compose + Caddy + Tailscale Funnel notes, (b) *Local dev* (api+web+worker minimal) clearly labeled not for production.
- Replace scattered env-var hunting with a **single annotated `.env.example` walkthrough** and a “first failure” troubleshooting table (permission denied, port in use, token mismatch, GPU not found).
- Consider a **hosted/reference demo instance** (even limited) link from marketing to reduce “install before try” friction for skeptics.

### 2) Mixed CLI/web mental models (TOML, stages, raw IDs)
**Pain:** Power-user concepts leak into UI (TOML wording, stage names, file IDs) and confuse newcomers.

**Concrete actions**
- In web UI, **hide TOML by default**; show it only in an “Advanced / developer” expandable with a short explanation (“generated config for reproducibility”).
- Replace/internalize jargon in primary flows: use labels like **“Setup steps”** instead of exposing raw stage IDs in novice mode; keep `minimization/equil-01/production` only in advanced details.
- For file selection, show **human names + sizes + type badges**; avoid exposing UUID file IDs in primary UI (use them only in copyable debug panels).
- Add an **in-app glossary tooltip** for: stage, equilibration, restraint, parameterization, view vs artifact, run token/lease (short, non-alarming text).
- Align naming across product surfaces: decide canonical terms (e.g. “Simulation job” vs “MD run”) and use them consistently in Web, API docs snippets shown to users, and marketing copy.

### 3) Opaque/raw failure logs
**Pain:** When prep/MD fails, users get logs/stack traces without ranked, actionable causes.

**Concrete actions**
- Add a **failure classifier** (backend heuristic pass over stderr/stdout + known patterns): e.g. PDBFixer missing residues, OpenFF/charge model issues, forcefield atom type coverage, OOM/GPU errors, disk full, packmol/memgen missing, permission errors.
- In Job Detail, show a **“What went wrong” panel** above raw logs: top 1–3 causes, confidence/“likely”, and suggested fixes (bulleted, with links to docs anchors).
- Include **copy-paste remediation snippets** where safe (e.g. “free space”, “check CUDA_VISIBLE_DEVICES”, “strip residues in prep”) and a “Report issue” bundle button (sanitized logs + job spec hash).
- For long logs, add **search + jump to errors** and collapse boilerplate; keep raw logs available but not the first thing novices see.
- Add **structured job error codes** in API/DB (even if initially mapped) so UI can render stable messages and docs can link by code.

### 4) No clear runtime/cost expectations
**Pain:** No ETA/cost guidance; queues and GPU waits feel like a black box.

**Concrete actions**
- Show **queue context clearly**: “Position in queue: N”, “Last similar job runtime: ~X (based on your recent runs or presets)” when data exists; otherwise honest “estimate unavailable.”
- Add **preset profiles** with rough guidance (ranges), e.g. “Small soluble protein+ligand (~50k atoms), equil+1 ns prod: often 2–8 hours on RTX 4090-class GPU” — clearly labeled as rough, hardware-dependent.
- Surface **resource hints** at submit time: atom/residue counts from parsed inputs, whether membrane adds cost, disk space estimate warning threshold.
- If multi-GPU or scheduling is added later, expose **worker availability** (e.g. “1 GPU online”) and avoid implying instant start.
- In marketing, align claims with reality (“queue time depends on shared GPU availability”) to reduce backlash.

### 5) Docs sprawl without a clear canonical path
**Pain:** Many markdown files; users don’t know what to read first or what is current.

**Concrete actions**
- Add a **root `START_HERE.md` (or `docs/README.md`)** that is the only “entrypoint”: links to *Install (self-host)*, *Quickstart (web)*, *Concepts*, *Troubleshooting*, *API*, *Contributing* — with “last verified” dates.
- Tag docs with status in headers: **Current / Reference / Design note / Historical** (or move design notes under `docs/design/`).
- Reduce duplication: pick one canonical page per topic (e.g. one “Deployment” page) and have others link to it.
- For the web app, add **in-app “Help” links** to the exact doc anchor for the current screen (New Job → help section, Errors → troubleshooting section).
- Add a **changelog or “what changed”** note for breaking env/config changes to reduce confusion after upgrades.

### 6) Unclear data retention/share policies in-product
**Pain:** Users don’t know how long data lives, who can access it, or how to share with collaborators/PI.

**Concrete actions**
- Add **Settings / Account page section “Your data”**: retention policy text (even if “kept until you delete or admin cleanup runs”), storage usage summary, and a clear delete/export path.
- Implement or document **job sharing**: at minimum “copy a read-only link” if same-org model exists later; for now, document current behavior (“private to your account”) prominently.
- On job pages, show **created/updated timestamps** and any scheduled cleanup warning if retention is enabled.
- Provide a **one-click export bundle** (zip/tar) of spec, key configs, final structures/trajectories pointers, analysis JSON, and manifest — described as the “repro/transfer package.”
- In admin docs/UI, surface **retention/orphan cleanup settings** (from service README) in plain language and link to runbook.

### Suggested sequencing (to reduce “hater” churn fastest)
- Week 1–2: failure classifier + “What went wrong” panel + deploy checklist script.
- Week 3–4: presets + runtime guidance + queue messaging + New Job copy cleanup (hide TOML/IDs by default).
- Ongoing: docs hub + in-app help links + data/sharing/export clarity.
