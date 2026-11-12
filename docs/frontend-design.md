# Lattice — frontend design

Working product name: **Lattice**. The frontend is a single-page web console for
the existing MD simulation service. It turns the API's job, stage, event, log,
and artifact primitives into a guided workflow that a bench scientist can use
without learning the CLI or the TOML configuration schema.

The first release covers the current protein–ligand MD workflow. The
navigation, job model, and visual language leave room for system preparation,
docking, free-energy calculations, and property prediction without a redesign.

- Source: `service/web/`
- Served at the same origin as the API (Caddy in front)
- Design tokens: `service/web/src/index.css`
- API client: `service/web/src/lib/api.ts`
- Query hooks: `service/web/src/lib/queries.ts`

## 1. Goals and non-goals

### Goals

- A non-technical user can go from a structure file to a queued simulation in
  under two minutes, with safe defaults at every step.
- A returning user can see what is running, what finished, and what needs
  attention at a glance.
- Failures are explainable: an error code, a plain-language message, the stage
  where it happened, and the next action.
- Live progress is pushed, not polled by hand.
- The browser never holds `SERVICE_API_TOKEN`; all browser traffic uses a
  short-lived, signed session cookie.
- The structure supports more computational-chemistry workflows later.

### Non-goals (v1)

- Multi-tenant user management, per-user accounts, or role-based access.
- Editing or re-uploading files inside an existing job.
- ~~A molecule viewer, trajectory player, or plotting suite.~~ Retired as a
  non-goal: see `docs/interactive-visualization-design.md` for the interactive
  and visual layer (structure viewing and editing, live monitoring charts,
  trajectory playback, checkpoint inspection) that builds on this design.
- Admin settings UI (queue limits, retention, and worker identity stay in
  environment configuration).
- Replacing machine API access: scripts continue to use bearer tokens.

## 2. Personas and jobs to be done

| Persona | Context | Primary jobs |
| --- | --- | --- |
| **Bench scientist** | Knows the chemistry, not the cluster | Start a standard simulation, check that it finished, download results |
| **Lab lead** | Owns the shared GPU box | See the queue, cancel runaway jobs, understand failures |
| **Computational chemist** | Configures protocols | Adjust ensemble, temperature, pressure, run length, integrator; retry from a stage |
| **Automation / CI** | Machine client | Unchanged: `Authorization: Bearer` against `/api/v1` |

The UI assumes a **shared lab login**. Every browser session is mapped to the
single owner `local`; attribution is by convention, not by user account. This is
deliberate for v1 and is the main boundary to revisit when per-user history
matters.

## 3. Product principles

1. **Defaults first, knobs second.** Presets produce a complete valid request.
   Advanced controls are visible but subordinate.
2. **One obvious next action.** Every page has a single primary button.
3. **Calm, not clinical.** Light neutral canvas, one teal accent, generous
   spacing, restrained motion. Status color is used only for status.
4. **Show the system working.** Stage timelines, live event feed, and progress
   bars make a long GPU job legible.
5. **Explain, then link.** Errors pair a plain message with the underlying
   `error_code`; technical detail is available, never required.
6. **Same-origin by construction.** No CORS, no tokens in URLs, no special
   browser transport.

## 4. Information architecture

```text
/                     Overview
/jobs                 Simulations (all jobs, filterable)
/jobs/:id             Job detail
/new                  New simulation wizard
*                     Not found
```

Sidebar:

- **Workspace** — Overview, Simulations
- **Platform** — System preparation, Docking, Free energy, Property prediction
  (marked “Soon”; present today to reserve the information architecture)
- Active workflow card — “Molecular dynamics”
- Footer — shared lab identity, sign out, API version

The URL is the state. The job detail page owns tabs for overview, stages,
events, logs, and artifacts so a link to a job is always shareable.

### Hierarchy

- **Overview** answers “is anything wrong, and what should I do next?” It shows
  active jobs, recent completions, queue depth, and a primary “New simulation”
  action.
- **Simulations** answers “where is job X?” A compact, scannable table with
  status, phase, progress, stage, and age; filters by status.
- **Job detail** answers “what is happening, and can I get the output?” Stage
  timeline, live progress, cancel/retry, logs, events, artifacts.
- **New simulation** answers “how do I start one?” A four-step wizard with a
  review-and-validate gate.

## 5. Core flows

### 5.1 Sign in

1. The app requests `GET /api/v1/session`.
2. Unauthenticated → login screen with the lab password.
3. `POST /api/v1/session` sets `md_session` (HttpOnly) and `md_csrf`
   (readable), then returns the session description.
4. Any `401` from the API dispatches `md:unauthorized`; the auth provider clears
   local state and returns to login.
5. Sign out calls `POST /api/v1/session/logout` with the CSRF header and clears
   both cookies.

### 5.2 Start a simulation

Wizard steps:

1. **Structure** — choose complex upload, separate protein + ligands, or a PDB
   ID. Uploads show progress; only allowlisted suffixes are accepted.
2. **System** — parameterization defaults (pH, padding, ionic strength), with a
   caption explaining what will be built.
3. **Simulation** — preset (quick check, standard, production, custom),
   equilibration stages, optional production, and advanced integrator/barostat
   controls. Durations are entered in ns and converted to resolved steps.
4. **Review** — human-readable summary, then `POST /api/v1/jobs/validate`.
   Validation must pass before “Start simulation” is enabled; create posts to
   `/api/v1/jobs` and navigates to the new job.

The wizard keeps a draft in component state. It is intentionally not persisted:
a reload starts clean rather than silently resuming a half-configured system.

### 5.3 Monitor

- The job detail page fetches the job and a page of events.
- It opens `EventSource` on
  `/api/v1/jobs/{id}/events/stream`, seeded with the last seen event ID.
- `event: job` appends an event and updates the job query cache.
- `event: progress` updates the progress snapshot.
- `event: end` closes the stream and triggers a final refetch.
- Polling (`GET /jobs/{id}` every 4 s) remains the fallback whenever SSE is
  unavailable or reconnecting.

### 5.4 Cancel and retry

- **Cancel** is available for queued, claimed, running, and canceling jobs. It
  is a destructive action and requires confirmation. Queued jobs cancel
  immediately; active jobs enter `canceling` until the worker acknowledges.
- **Retry** is available after a terminal state with four modes:
  - `resume` — continue from the last checkpoint.
  - `restart` — rerun from the beginning.
  - `restart_stage` — rerun from a chosen stage.
  - `reparameterize` — rebuild the system before continuing.
  The modal explains what each mode preserves.

### 5.5 Inspect results

- **Artifacts** are listed by stage and kind with size and download actions.
- **Logs** list allowlisted worker logs with a bounded tail viewer and a full
  download link.
- **Events** render the persisted audit-style timeline.
- **Configuration** shows the generated `config.toml` and the resolved plan for
  reproducibility.

### 5.6 System preparation: membrane embedding

The **System preparation** workspace (reachable from the sidebar) lets users
embed a protein structure in a lipid bilayer before simulation. This is an
optional step: users can still upload a raw structure directly into the MD
wizard, but membrane proteins benefit from a pre-equilibrated bilayer.

Flow:

1. **Upload** a protein structure (PDB or mmCIF) via the file dropzone.
2. **Configure** the bilayer: lipid type (POPC, POPE, DPPC, DLPC, DSPC, SOPC),
   box padding, optional membrane orientation, and ionic strength.
3. **Submit** — `POST /api/v1/prep/membrane` queues a prep job and returns
   immediately.
4. **Poll** — the page polls `GET /api/v1/prep/jobs/{id}` every 3 seconds
   until the job reaches `completed` or `failed`. The response carries
   `phase`, `progress_percent`, and `progress_message`; for membrane
   embedding the worker parses packmol’s log and reports the block and
   loop it is on (for example `packing WAT.pdb (block 5/9, loop 3/20)`).
   Packing a solvated bilayer moves ~80k molecules and can take many
   minutes, so the progress detail matters: a bare “running” status gives
   the user no way to tell work from a hang.
5. **Use** — on completion, the embedded PDB and topology (PSF) are registered
   as files. A “Use embedded system in simulation” button deep-links to the
   new-job wizard with the embedded PDB pre-selected as the complex file.

If Packmol-Memgen is not configured on the server (`PACKMOL_PATH` unset), the
workspace shows a clear message and the feature is unavailable. Capabilities
expose `prep_workflows.membrane_embed.enabled` so the UI can adapt.

## 6. Visual design system

### 6.1 Direction

A light, calm scientific console: off-white canvas, white cards, fine gray
rules, deep ink text, and a single teal accent. The palette avoids neon “GPU
dashboard” styling and prioritizes long reading sessions and dense tables.

### 6.2 Tokens

Defined in `service/web/src/index.css` using Tailwind CSS 4 `@theme`:

| Token | Value | Use |
| --- | --- | --- |
| `canvas` | `#f5f7f8` | Page background |
| `surface` | `#ffffff` | Cards, sidebar |
| `surface-muted` | `#f8fafb` | Subtle fills |
| `line` / `line-strong` | `#e4e9ed` / `#d3dbe1` | Borders and dividers |
| `ink` | `#0e1b25` | Primary text |
| `ink-soft` | `#33424e` | Body text |
| `muted` | `#6b7b88` | Secondary text |
| `faint` | `#93a1ad` | Metadata, placeholders |
| `brand-500` | `#17a394` | Primary action, active state |
| `brand-700` | `#0e6b62` | Hover, emphasis |

Semantic status colors are applied through badges only:

- queued — amber/neutral
- claimed / running — teal
- canceling — amber
- completed — green
- failed — red
- canceled — gray

Typography: Inter for UI, JetBrains Mono for IDs, step counts, and code.
Radii: 16 px cards, 10 px controls. Shadows: one restrained card shadow and one
floating shadow for menus/modals.

### 6.3 Components

Primitives live in `src/components/ui/`:

- `Button` — primary, secondary, ghost, destructive; three sizes; loading state.
- `Badge` — status and metadata.
- `Card` — section container with optional header/actions.
- `Form` — labelled fields, hints, errors, and grouped sections.
- `Modal` — confirmation and retry dialogs.
- `Progress` — determinate and indeterminate.
- `EmptyState` — plain-language next step.
- `Toast` — transient success and error feedback.
- `CopyButton`, `FileDropzone`.

Feature components live with their page (`components/jobs/`, `upload/`).

### 6.4 Motion and accessibility

- Motion is limited to a 350 ms fade-up for page entry and a soft pulse for
  active status. No parallax or decorative animation.
- Focus rings are visible on every interactive element.
- Status is never conveyed by color alone: badges include text.
- Tables collapse to stacked cards on narrow screens; the sidebar becomes a
  drawer below `lg`.
- The wizard is keyboard-navigable; destructive actions are labelled and
  confirmed.
- Respect reduced motion through Tailwind's `motion-safe` utilities where
  animation is added.

## 7. Technical architecture

### 7.1 Stack

- React 19 + TypeScript
- Vite 8
- React Router 7
- TanStack Query 5 for server state
- Tailwind CSS 4 with CSS-first tokens
- lucide-react icons
- No global state library: auth and toasts use small providers; URL and query
  cache own the rest.

### 7.2 Runtime shape

```text
Browser
  │  same origin, cookie auth
  ▼
Caddy ── /api/*, /healthz ──────────────► FastAPI (api:8000)
  │
  └── everything else ──────────────────► nginx SPA (web:80)
```

Development mirrors this: Vite serves the app on `:5173` and proxies `/api` and
`/healthz` to `127.0.0.1:8000`, so cookies and `EventSource` behave exactly as
in production.

### 7.3 Data flow

- `api.ts` owns fetch, JSON/text parsing, CSRF headers, upload XHR progress,
  download URLs, and typed errors (`ApiError` with status, code, details,
  request ID).
- `queries.ts` owns query keys, cache lifetimes, and adaptive polling
  (`refetchInterval` only while a job is active).
- `useJobStream.ts` owns SSE lifecycle, reconnect with `after_id`, and cache
  updates.
- Pages never call `fetch` directly.

Query keys are hierarchical (`["job", id, ...]`) so a job update can invalidate
one job without touching the list, and mutations can invalidate both.

### 7.4 Error handling

- API errors render the server's plain message and retain the `error_code` for
  support.
- `network_error` and HTTP 5xx show a retry affordance rather than a raw stack.
- 401 returns to login; 403 from a missing CSRF cookie surfaces as a session
  problem and prompts re-login.
- 429 shows the retry delay from `Retry-After`/`details`.
- 507 (`insufficient_storage`) and queue-limit 429 are explained in context, not
  as generic failures.

## 8. Session and CSRF model

### 8.1 Why a gateway

The static `SERVICE_API_TOKEN` is powerful and long-lived. Putting it in
JavaScript, `localStorage`, or a query string would expose it to any XSS or
shared URL. Instead, the FastAPI app now issues a signed browser session.

### 8.2 Login

`POST /api/v1/session` with `{ "password": "..." }`:

- compares against `WEB_PASSWORD` or a scrypt `WEB_PASSWORD_HASH`
  (constant-time);
- is rate-limited per client IP (`WEB_LOGIN_ATTEMPTS_PER_MINUTE`);
- sets `md_session` — HttpOnly, `SameSite=Lax`, `Secure` by default, path `/`,
  TTL `WEB_SESSION_TTL_SECONDS`;
- sets `md_csrf` — readable by JavaScript, same lifetime and flags;
- returns owner, issue time, expiry, and auth method.

Sessions are stateless: HMAC-SHA256 over a base64url JSON payload containing
subject, issued-at, expiry, and a nonce. The key is `WEB_SESSION_SECRET`, falling
back to `SERVICE_API_TOKEN`. Rotating the secret invalidates all sessions.

### 8.3 Authorization

`security.py` accepts either:

1. `Authorization: Bearer SERVICE_API_TOKEN` (machine clients), or
2. a valid `md_session` cookie (browsers).

Cookie-authenticated mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`) must
echo the readable `md_csrf` value in `X-CSRF-Token`. The check is
constant-time. `SameSite=Lax` plus double-submit is sufficient for this
single-origin deployment; no CORS credentials are required.

The SPA sends `credentials: "same-origin"` and adds the CSRF header
automatically for mutations, including the XHR upload path.

### 8.4 Threat notes

- XSS can act as the logged-in user for the session lifetime; a strict CSP and
  dependency hygiene remain important. The session cannot be exfiltrated as a
  reusable bearer token beyond its TTL.
- CSRF is blocked by the double-submit token for mutations; `GET` routes are
  read-only.
- `/internal/*` is answered with 404 by Caddy and requires the separate worker
  token.
- HTTPS is expected in production. `WEB_COOKIE_SECURE=false` exists only for
  local HTTP development.

## 9. Extensibility model

The backend is MD-specific today, but the UI separates **workflow** from
**platform shell**:

- The sidebar reserves a “Platform” group for future workspaces.
- The job model is generic: name, status, stages, events, logs, artifacts.
  New workflows can reuse the same overview, list, detail, and result pages.
- The new-job wizard is organized by workflow-specific steps behind a shared
  shell; only the draft builder and step components change per workflow.
- Capabilities remain the source of truth. Dropdowns, limits, and defaults are
  read from `GET /api/v1/capabilities` rather than hard-coded.

### Adding a workflow

1. Add a workflow descriptor (id, label, icon, description, route prefix).
2. Add a draft type and payload builder next to `pages/new-job/draft.ts`.
3. Add step components; reuse structure upload, review, and validation.
4. Point the list and detail pages at the workflow's API namespace once the
   backend exposes it.
5. Add the descriptor to the sidebar registry and dashboard cards.

Until the backend grows namespaces, new entries stay disabled with a “Soon”
badge. That keeps the promise visible without shipping dead ends.

## 10. Backend contract touchpoints

| UI need | Endpoint |
| --- | --- |
| Login / session | `GET`, `POST /api/v1/session`; `POST /api/v1/session/logout` |
| Defaults and limits | `GET /api/v1/capabilities` |
| Upload structure | `POST /api/v1/files` |
| Validate draft | `POST /api/v1/jobs/validate` |
| Create job | `POST /api/v1/jobs` |
| List / filter jobs | `GET /api/v1/jobs` |
| Job detail and progress | `GET /api/v1/jobs/{id}` |
| Live updates | `GET /api/v1/jobs/{id}/events/stream` |
| Event history | `GET /api/v1/jobs/{id}/events` |
| Generated config | `GET /api/v1/jobs/{id}/config` |
| Resolved spec | `GET /api/v1/jobs/{id}/spec` |
| Cancel / retry | `POST /api/v1/jobs/{id}/cancel`, `/retry` |
| Artifacts | `GET /api/v1/jobs/{id}/artifacts[/{artifact_id}]` |
| Logs | `GET /api/v1/jobs/{id}/logs`, tail, download |
| Account-wide activity feed | `GET /api/v1/jobs/events` |
| Workflows (base systems) | `GET`, `POST /api/v1/workflows`; `GET /api/v1/workflows/{id}` |
| Launch workflow variants | `POST /api/v1/workflows/{id}/variants` |
| System preparation | `POST /api/v1/prep/system-prep`; `GET /api/v1/prep/jobs/{id}` |
| Membrane embedding | `POST /api/v1/prep/membrane`; `GET /api/v1/prep/jobs/{id}` |

Wire types mirror `service/api/app/schemas.py` and live in
`src/lib/types.ts`. When the contract changes, update both sides together.

## 11. Deployment

The Compose stack has five services: `migrate`, `api`, `worker`, `prep-worker`,
`web`, and `caddy`.

- `web` builds the SPA with Node and serves `dist/` from nginx.
- nginx handles SPA history fallback, immutable caching for hashed assets, and
  baseline security headers.
- Caddy terminates TLS, proxies `/api/*` and `/healthz` to the API, returns 404
  for `/internal/*`, and sends everything else to `web:80`.
- The API and web containers stay unpublished; they are only exposed to Caddy.
- `prep-worker` runs packmol-memgen for membrane embedding jobs claimed from
  the internal API. It requires `PACKMOL_PATH` and the packmol-memgen Python
  package.

Browser login requires `WEB_PASSWORD` or `WEB_PASSWORD_HASH`, plus a signing
secret. Membrane embedding requires `PACKMOL_PATH` set to the packmol-memgen
executable. See `service/.env.example` for the full set.

```bash
cd service
cp .env.example .env
# Set SERVICE_API_TOKEN, WORKER_TOKEN, WEB_PASSWORD (or hash),
# WEB_SESSION_SECRET, PACKMOL_PATH, MD_SERVICE_DOMAIN, and host paths.
docker compose --env-file .env up -d --build
```

## 12. Operations runbook

### 12.1 Enabling membrane embedding

1. Install `packmol` (e.g. `apt-get install packmol`) on the prep worker host.
2. Install `packmol-memgen` and its Python dependencies (pandas, matplotlib,
   numba, scipy, pdb2pqr, gemmi, biopython).
3. Set `PACKMOL_PATH` to the packmol-memgen executable path in `.env`.
4. Start the `prep-worker` service: `docker compose up -d prep-worker`.
5. Verify prep is enabled: `GET /api/v1/capabilities` should show
   `prep_workflows.membrane_embed.enabled: true`.

### 12.2 Monitoring prep jobs

- List all prep jobs: `GET /api/v1/prep/jobs`
- Check a specific job: `GET /api/v1/prep/jobs/{prep_job_id}`
- The prep worker heartbeat and claim status are internal-only (not exposed
  through Caddy).

### 12.3 Canceling a prep job

- `POST /api/v1/prep/jobs/{prep_job_id}/cancel` requests cancellation.
- Queued jobs are canceled immediately; claimed/running jobs enter `canceling`
  until the prep worker acknowledges the stop request.

### 12.4 Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Prep endpoints return 503 | `PACKMOL_PATH` not set | Set `PACKMOL_PATH` in `.env` and restart API |
| Prep jobs stay `queued` | Prep worker not running | Start `prep-worker` service |
| Prep job fails with `packmol-memgen` error | Invalid input structure | Verify PDB/mmcif file is valid |
| Prep job fails with `prep_start_failed` | packmol-memgen not executable | Check `PACKMOL_PATH` points to executable |

### 12.5 Cleanup

Prep job output files (embedded PDB) are registered as normal file records and
are subject to the same retention policy as other uploads. Use
`python -m app.cleanup` to remove orphaned files and workspaces.


## 13. Local development

```bash
# Terminal 1 — API
cd service/api
export DATABASE_URL="sqlite:///$PWD/dev.db"
export DATA_ROOT="$PWD/dev-data"
export SERVICE_API_TOKEN="dev-service-token"
export WORKER_TOKEN="dev-worker-token"
export WEB_PASSWORD="dev-lab-password"
export WEB_SESSION_SECRET="dev-session-secret"
export WEB_COOKIE_SECURE="false"
export SIMULATION_PLATFORM="CPU"
export ALLOW_PDB_DOWNLOAD="false"
../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — SPA
cd service/web
npm install
npm run dev
# http://127.0.0.1:5173
```

`npm run typecheck` and `npm run build` must pass before deployment.

## 14. Phased roadmap

### Phase 1 — shipped

- Shared-login session gateway and CSRF protection
- Overview, simulations list, job detail with live stages/events/progress
- Four-step new-simulation wizard with validation
- Artifact and log inspection
- Responsive shell, empty/error/loading states, production container

### Phase 2 — workflow depth

- Saved protocol templates (“standard CHARMM36 ligand run”)
- Duplicate a past job with edited parameters
- Batch submit several ligands against one protein
- Failure insights: map common `error_code`s to remediation tips
- Optional persisted wizard draft

### Phase 3 — platform breadth

- System preparation workspace (parameterize and inspect without simulating)
- Docking and free-energy workflows behind the same job shell
- Cross-workflow search and a unified activity feed
- Admin panel for queue limits, retention, and worker status
- Interactive visualization layer — structure viewer with selection-driven
  editing, derived trajectory views and playback, live monitoring charts, and
  checkpoint inspection; see `docs/interactive-visualization-design.md` for
  the phased plan (V1 viewer foundation → V2 visual builder → V3 analysis
  and playback → V4 live views)

### Phase 4 — collaboration

- Per-user accounts and attributions
- Shareable read-only links (signed, expiring)
- Comments and run annotations
- Exportable run reports

## 15. Quality checklist

Before a frontend change ships:

- `npm run typecheck` and `npm run build` pass.
- Login, logout, and session expiry return to a usable state.
- Mutations work with CSRF; a missing token fails closed.
- The new-job wizard validates before creating, and server validation errors
  appear on the review step.
- Live updates stop when a job reaches a terminal state.
- Cancel and retry use explicit confirmation and explain their effect.
- Every empty state names the next action.
- Narrow viewport (375 px) and keyboard-only navigation remain usable.
- No secret, bearer token, or internal URL appears in the bundle.
