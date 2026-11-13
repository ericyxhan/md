# MD Service

FastAPI control plane and OpenMM GPU worker for the existing checkpointed
simulation workflow. The full design is in
[`../docs/service-implementation-plan.md`](../docs/service-implementation-plan.md).

## Status

Implemented in this repository:

- API scaffold, settings, SQLite engine with WAL/foreign-key/busy-timeout
  pragmas, and an Alembic-owned schema.
- Bearer-token authentication and a separate worker-token check.
- Immutable file uploads with streaming SHA-256 and size/suffix limits.
- Pydantic job requests with `extra="forbid"` and no raw TOML, paths,
  executables, force fields, or platform properties.
- Canonical job specification, generated stage names (`minimization`,
  `equil-01`, ..., `production`), safe TOML generation, and final validation
  through the simulation code's `config.load_config()`.
- Job creation, workspace materialization, `job.json`, list, detail, config,
  spec, events, dry validation, and queue position.
- Internal worker protocol at `/internal/v1`: heartbeat with lease extension,
  atomic oldest-first claim, progress, stage reconciliation, and finish with
  artifact validation.
- Public cancellation and retry (`resume`, `restart`, `restart_stage`,
  `reparameterize`) with queue reordering by re-enqueue time.
- Run-token fencing for stale workers, lease expiry reaper, and a worker-token
  check separate from the public bearer token.
- Worker claim/launch/poll loop: fixed command construction, process-group
  cancellation (SIGINT, SIGTERM, SIGKILL), progress polling, stage-manifest
  reconciliation, artifact scanning, and finish reporting.
- Simulation progress instrumentation: `simulate.py --progress-file` writes an
  atomic JSON document at every lifecycle boundary and between bounded
  simulation chunks, and SIGTERM follows the same graceful checkpoint-preserving
  path as Ctrl-C.
- API and worker images, a one-shot migration service, a Compose stack with
  host bind mounts, healthchecks, and a Caddy reverse proxy that hides
  `/internal/*`.
- User accounts: an email address, a first name, a last name, and a password
  of the reader's choosing. Every upload, job, preparation, workflow, and
  audit row belongs to exactly one account, and every file lives inside that
  account's own directory under `DATA_ROOT`. The account the lab used before
  accounts existed is the administrator, and the data it produced stays
  reachable after the upgrade.
- Worker tests with a fake API and fake runner, including success, failure,
  cancellation, escalation, stale tokens, and unsafe claim paths.
- Artifact listing and ID-only downloads with ownership checks and confined,
  symlink-free path resolution.
- Log listing, bounded tail reads, and downloads for worker and registered
  workflow logs.
- Server-sent events at `/jobs/{id}/events/stream` with `Last-Event-ID`
  reconnect support; polling `GET /jobs/{id}` remains the fallback.
- Request IDs, structured JSON request logs, per-owner token-bucket rate
  limiting, and an append-only audit trail for job mutations.
- Queue and free-disk admission checks plus opt-in retention and orphan
  cleanup hooks.
- A backup/restore runbook and a tested SQLite `.backup` restore path.
- A same-origin React web console (`service/web/`) with account sign-in and
  self-service registration, signed HttpOnly sessions, CSRF protection, guided
  job creation, live progress, logs, events, and artifact downloads. The
  frontend design is in
  [`../docs/frontend-design.md`](../docs/frontend-design.md).
- System preparation: membrane embedding via Packmol-Memgen (`POST
  /api/v1/prep/membrane`, `GET /api/v1/prep/jobs/{id}`). Upload a protein
  structure (PDB or mmCIF), embed it in a lipid bilayer, then use the resulting
  embedded PDB as the input for a new MD job. Requires `PACKMOL_PATH` and the
  `packmol-memgen` Python package on the API server; disabled by default.

## Docker Compose

The API image is built from the repository root; the worker image derives from
the simulation image and adds the worker plus `httpx`. Rebuild the simulation
image after changing `simulate.py`, `stages.py`, `config.py`, or the other
workflow modules so the worker image picks up the new code:

```bash
cd /path/to/the/repository
docker build -t openmm-cuda12:8.6.1 .
docker build -t md-worker:local service/worker
```

The root and worker Dockerfiles clear the executable-stack flag on the
conda-forge PyTorch library with `patchelf`. Newer kernels refuse to load it
otherwise, which breaks the NAGL charge model used by `openff-2.3.0`
parameterization.

Prepare host directories owned by the API UID (10001). The worker runs as root
in the reference Compose file because GPU device access is host-specific; test
a non-root worker and add it to the required device groups before relying on
that in production:

```bash
sudo mkdir -p /srv/md-service/{db,data/users,data/cache,backups}
sudo chown -R 10001:10001 /srv/md-service
sudo chmod 750 /srv/md-service
```

Create `service/.env` from `.env.example`, then start the stack:

```bash
cd service
cp .env.example .env
# Set SERVICE_API_TOKEN, WORKER_TOKEN, MD_SERVICE_DOMAIN, and host paths.
# Set ADMIN_PASSWORD_HASH (or WEB_PASSWORD_HASH) and WEB_SESSION_SECRET for
# the browser console. Generate each token separately, for example:
#   python -c 'import secrets; print(secrets.token_urlsafe(48))'
docker compose --env-file .env up -d --build
docker compose ps
```

Caddy publishes only `/api/*` (currently `/api/v1/*`), `/healthz`, and the
single-page app; `/internal/*` always returns 404. The API and web containers
are not published on host ports. For local API development without Caddy, run
Uvicorn and Vite directly as shown below.

## Accounts

The service is open to anyone who can reach it. A reader creates their own
account with an email address, a first name, a last name, and a password of
their choosing; there is no shared lab password any more.

### Creating an account

Registration lives at `POST /api/v1/users` and is public. The web console
offers it on the sign-in page ("Create an account"). The account is signed in
immediately, so a new reader does not type the password twice.

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","first_name":"Ada","last_name":"Lovelace","password":"correct horse battery"}' \
  "$BASE/users"
```

The response is the account without its password hash, and the session
cookies are set on the response, exactly as they are after a sign-in.

Two deployment settings control who may join:

- `REGISTRATION_ENABLED=false` closes registration. Accounts are then created
  by an administrator, with `scripts/create_account.py` or the administrator
  console.
- `REQUIRE_ADMIN_APPROVAL=true` creates accounts inactive. They cannot sign
  in until an administrator activates them.

Registration is rate limited per client address and the sign-in form is rate
limited per client address, so a public endpoint cannot be used to guess
passwords or to fill the accounts table with junk.

### Signing in

`POST /api/v1/session` takes the email address and the password and returns
the signed session cookies. `GET /api/v1/session` describes the current
session, including the account it belongs to.

```bash
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"correct horse battery"}' \
  "$BASE/session"
```

Passwords are stored as self-describing scrypt hashes: the work factors are
part of the hash, so they can be raised later without invalidating the
passwords that are already stored. The plaintext is never written to disk.

### The administrator

The administrator is an ordinary account with `is_admin` set. It can

- list every account, with the number of jobs, files, and preparations each
  one owns;
- deactivate an account, which signs it out and blocks new sign-ins without
  touching the data it produced;
- promote another account to administrator; and
- reset an account's password.

The administrator console is at `/admin/users` in the web console, and the
API is at `/api/v1/users` (`GET`, `GET /{id}`, `PATCH /{id}`). The API refuses
a non-administrator with 403.

An administrator cannot deactivate or demote itself, so a deployment cannot
be left without somebody who can undo a mistake.

Machine clients are unaffected: `SERVICE_API_TOKEN` still authenticates
against the public API, and it acts as the administrator. That is what keeps
the CLI examples in this README working.

### Upgrading an existing deployment

The account the lab used before accounts existed becomes the administrator,
and everything it produced moves to it.

1. `alembic upgrade head` runs migration `0009`, which creates the `users`
   table, inserts the administrator, and re-points the `owner_id` of every
   existing job, file, preparation, workflow, and audit row at it. The
   administrator's id is fixed (`00000000-0000-4000-8000-000000000001`) so it
   never has to be rewritten again.
2. The administrator's password is the lab password. `ADMIN_PASSWORD_HASH`
   wins; when it is empty `WEB_PASSWORD_HASH` is used, and a plaintext
   `WEB_PASSWORD` is hashed once, during the migration.
3. The data on disk moves from the flat layout into the account's directory:

   ```bash
   docker compose -f compose.yml run --rm --no-deps api \
       python /app/scripts/migrate_user_data.py --dry-run
   docker compose -f compose.yml run --rm --no-deps api \
       python /app/scripts/migrate_user_data.py
   ```

   The script is idempotent: anything already in the new layout is left
   alone, so it can be run again after a partial failure.

`scripts/set-admin-password.sh` sets the administrator's password and
rewrites `.env` with only the hash in it.

The stored hash is the authoritative one: the API leaves an administrator's
password alone once one is set, so that a password changed from the account
page survives a restart. The script therefore updates the account as well as
`.env`, running the update inside the API container as the service account.
It prints the new password once when it generates one.

## Shared contract

Several values are needed by more than one file: the port the API listens on,
the port the edge publishes, the account the containers run as, the paths they
mount, and the route prefixes. When those values are written out separately in
compose.yml, the Caddyfile, the Dockerfiles, the nginx config, the systemd
units and the frontend, a change to one of them silently desynchronises the
others. That is how the edge ended up proxying to a port nobody was listening
on, and how the prep worker ended up writing files the API could not read.

`contract.env` owns those values. Everything else refers to them:

| File | How it refers to the contract |
|---|---|
| `compose.yml` | `${MD_API_PORT:-8000}` and friends, plus build arguments |
| `Caddyfile` | `{$MD_API_PORT:8000}` placeholders |
| `api/Dockerfile` | `ARG MD_SERVICE_UID=10001`, `USER ${MD_SERVICE_UID}:${MD_SERVICE_GID}` |
| `worker/prep_worker.Dockerfile` | the same account, so the two can read each other's files |
| `web/nginx.conf` | `listen ${MD_WEB_PORT};`, substituted by nginx's entrypoint |
| `scripts/*.service` | `EnvironmentFile=` and `${MD_EDGE_PORT}` |
| `scripts/*.sh` | sourced from `contract.env` by `00-env.sh` |

The file holds no secrets. Deployment secrets stay in `.env`, which is layered
on top of it, so a secret always wins over a contract default.

### Checking it

```bash
python3 service/scripts/check-contract.py
```

It reads every file above and fails when a copy disagrees with the contract.
A value may be written literally or as a reference; a literal is checked
against the contract, and a reference's fallback has to match it too, so a
build that runs without the contract file still produces the same
deployment.

The same check runs as part of the test suite
(`tests/test_service_contract.py`), which also confirms that the checker
still detects a value that has drifted in either direction.

### Preflight

```bash
cd service
./scripts/preflight.sh
```

It runs the contract check, verifies the host prerequisites (the env file, the
required secrets, a configured browser login, the database and data
directories, free disk space, and that the edge port is still bound to
loopback), and then checks the running stack and the public tunnel.
`launch-all.sh` runs it first and refuses to start a deployment that fails.

### Changing a value

1. Edit `contract.env`.
2. Run `python3 service/scripts/check-contract.py`. It lists every copy that
   still holds the old value.
3. Update the copies it names, then run it again until it passes.
4. Rebuild the affected images and restart the stack.

## Public deployment

The stack is published to the internet through a Tailscale Funnel tunnel. The
funnel terminates TLS and forwards to Caddy, which listens on plain HTTP on
the loopback interface only. The SPA and the API therefore share one origin,
so the browser session cookie, the CSRF token, artifact downloads and the
event stream all work without any cross-origin handling.

```
browser ──HTTPS──► Tailscale Funnel ──► Caddy (127.0.0.1:8080) ──► api:8000
                                              └──► web:80 (SPA)
```

Nothing listens on a public port: the funnel connects outward, so the host
needs no public IP and no router configuration. That also means the service
is reachable from a home connection behind NAT.

Funnel is the only free ingress that gives a stable hostname, working
server-sent events, and a valid certificate without a domain. Cloudflare
quick tunnels change hostname on every restart and explicitly do not support
SSE; ngrok's free tier caps data transfer at 1 GB per month, which a single
trajectory would exhaust.

### One-time setup

```bash
cd service
./scripts/setup-public-access.sh
```

The script installs Tailscale into `~/.local/share/tailscale-pkg/` and runs it
in **userspace mode**, so it needs no root. It then registers two user
systemd units in `~/.config/systemd/user/`:

| Unit | Role |
|---|---|
| `tailscaled.service` | the Tailscale daemon |
| `md-funnel.service` | publishes `http://127.0.0.1:8080` over the funnel |
| `md-backup.timer` | nightly backup of the database and job data |

`loginctl enable-linger` keeps both running after logout and reboot.

Two steps need a browser, because they authenticate as your account:

1. `tailscale --socket=$HOME/.local/share/tailscale/tailscaled.sock up
   --accept-dns=false --ssh=false --hostname=$(hostname -s)` prints a login
   URL. Sign in and the node joins your tailnet.
2. The funnel command prints a second URL to enable Funnel on the tailnet.
   That adds the `funnel` node attribute to the tailnet access controls:

   ```json
   {
     "nodeAttrs": [
       { "target": ["autogroup:member"], "attr": ["funnel"] }
     ]
   }
   ```

The public hostname is printed by `journalctl --user -u md-funnel.service` and
looks like `https://<machine>.<tailnet>.ts.net`. It does not change across
restarts.

Kernel mode is faster than userspace mode but requires `CAP_NET_ADMIN`; if
you install the official package with root you can drop `--tun=userspace-networking`
from `tailscaled.service`.

### Verify the deployment

```bash
# The tunnel reaches the service.
curl -s -o /dev/null -w "%{http_code}\n" https://<machine>.<tailnet>.ts.net/healthz

# Worker routes are not reachable from the internet (404, not 401).
curl -s -o /dev/null -w "%{http_code}\n" https://<machine>.<tailnet>.ts.net/internal/v1/jobs/claim

# The client address reaches the API rather than the local proxy.
docker compose --env-file .env logs api | grep request.completed | tail -1
```

The last command must show a public IP address in `client_ip`. If it shows
`172.19.0.1`, the tunnel did not forward the client address and the per-IP
login limiter is collapsing into a single bucket.

### Client address handling

Caddy discards forwarding headers it cannot vouch for, so it is configured
with `trusted_proxies` for the loopback and private ranges and rewrites
`X-Forwarded-For` to the single address it resolved. The API reads that
header (`TRUST_FORWARDED_FOR=true`, on by default) and uses it for the
per-IP rate limiter and the audit trail. Set `TRUST_FORWARDED_FOR=false` when
running the API directly, without a proxy in front.

### Backups

```bash
cd service
./scripts/backup.sh               # writes to BACKUP_DIR from .env
```

The database is copied with SQLite's online backup API, which is safe against
a live WAL database. The data root is copied with a plain `tar`. Every
container that writes into it runs as the contract service account, so the
whole tree is readable and the copy is complete without sudo; if it is not,
the script falls back to copying through a container, which reads as root.

It is scheduled as a user systemd timer, so it runs unattended:

```bash
systemctl --user list-timers md-backup.timer
systemctl --user start md-backup.service     # run one now
```

The timer fires just after 03:00 with a randomised delay, and catches up on
a missed run after a reboot.

### Keeping it running

- `tailscaled.service` and `md-funnel.service` are user systemd units, enabled
  with linger so they survive logout and reboot.
- The containers use `restart: unless-stopped`.
- The host must stay powered on and awake. Disable sleep and hibernation.
- Funnel traffic is bandwidth-limited by Tailscale and shares relay capacity.
  Interactive viewing uses the derived solute-focused views, which are small;
  downloading a raw trajectory is the slow path.

### Deploying an update

```bash
cd service
./scripts/stop-all.sh
./scripts/launch-all.sh
```

The tunnel is unaffected by a stack restart. The SPA is rebuilt by
`launch-web.sh`, so a frontend change needs that step.

## Local development

From the repository root:

```bash
cd service/api
export DATABASE_URL="sqlite:///$PWD/dev.db"
export DATA_ROOT="$PWD/dev-data"
export SERVICE_API_TOKEN="dev-service-token"
export WORKER_TOKEN="dev-worker-token"
export SIMULATION_PLATFORM="CPU"
export ALLOW_PDB_DOWNLOAD="false"
# Optional: enable system preparation (membrane embedding)
export PACKMOL_PATH="/usr/bin/packmol"

../../.venv/bin/python -m pip install -r requirements.txt
../../.venv/bin/alembic upgrade head
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Or with the repository virtual environment already active:

```bash
cd service/api
alembic upgrade head
uvicorn app.main:app --reload
```

Health checks do not require a token:

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/readyz
```

## Running the worker

The worker is a separate process. It never opens SQLite and only talks to the
internal API with `X-Worker-Token`:

```bash
cd service/worker
export API_URL="http://127.0.0.1:8000"
export WORKER_TOKEN="dev-worker-token"
export WORKER_ID="gpu-0"
export DATA_ROOT="/path/to/the/same/data-root-as-the-api"
export SIMULATE_PATH="/path/to/simulate.py"
export SIMULATE_CWD="/path/to/the/simulation/code"

# Claim and run at most one job, then exit.
../../.venv/bin/python worker.py --once

# Run forever: heartbeat, claim, launch, poll, finish, repeat.
../../.venv/bin/python worker.py
```

The worker removes any stale `progress.json`, launches the fixed command in a
new session, sends progress only when it changes (and at least every 30
seconds), reconciles each `stage.json`, and reports artifacts after the process
exits. Cancellation sends SIGINT, then SIGTERM after 30 seconds, then SIGKILL
after 10 more seconds. `simulate.py` writes progress atomically and exits 130
on either signal after preserving the current stage checkpoint.

## Usage

```bash
TOKEN=dev-service-token
BASE=http://127.0.0.1:8000/api/v1

# Upload a complex.
FILE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  -F "file=@../../test_inputs_7yae/protein.pdb" \
  "$BASE/files" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

# Create a short CPU job.
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\":\"smoke test\",\"input\":{\"mode\":\"complex\",\"complex_file_id\":\"$FILE_ID\"},\"equilibration\":[{\"duration_ps\":0.02,\"report_interval\":10,\"trajectory_interval\":10,\"checkpoint_interval\":10}],\"production\":{\"enabled\":false}}" \
  "$BASE/jobs"
```

Use `POST /api/v1/jobs/validate` to resolve a plan without writing a job, and
`GET /api/v1/jobs/{id}` to poll status, stage rows, and progress.

Cancel or retry a job:

```bash
# Queued jobs become canceled immediately. Active jobs enter "canceling"
# until the worker acknowledges the stop request.
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE/jobs/$JOB_ID/cancel"

# Retry a terminal job.
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"resume"}' "$BASE/jobs/$JOB_ID/retry"
```

### Artifacts and logs

Artifacts are registered when the worker reports completion. List them with an
optional `kind` or `stage` filter, then download by artifact ID only:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/jobs/$JOB_ID/artifacts"
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/jobs/$JOB_ID/artifacts?kind=trajectory&stage=production"
curl -s -L -H "Authorization: Bearer $TOKEN" \
  -o trajectory.dcd "$BASE/jobs/$JOB_ID/artifacts/$ARTIFACT_ID"
```

The API resolves every path relative to the job workspace, rejects absolute
paths, `..`, and symlinks, and serves downloads as attachments. There is no
query-string path parameter.

Worker logs are available while a job is running. The allowlisted names are
`logs/worker.log`, `logs/simulate.stdout`, and `logs/simulate.stderr`; completion
reports can also register log artifacts under `outputs/`.

```bash
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/jobs/$JOB_ID/logs"

# Bounded JSON tail (defaults: 200 lines, at most LOG_TAIL_MAX_BYTES).
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/jobs/$JOB_ID/logs/logs/worker.log/tail?lines=100"

# Full download as an attachment.
curl -s -L -H "Authorization: Bearer $TOKEN" \
  -o worker.log "$BASE/jobs/$JOB_ID/logs/logs/worker.log"
```

### Live events

Use server-sent events to follow phase, stage, completion, and progress changes:

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  "$BASE/jobs/$JOB_ID/events/stream"
```

Frames are `event: job` for persisted job events, `event: progress` for a
compact progress snapshot when it changes, and `event: end` when the job is
terminal. Reconnect with the `Last-Event-ID` header (or `?after_id=N`) to resume
after the last event you saw. The stream sends keep-alive comments while idle.
Clients that cannot use SSE can poll `GET /jobs/{id}` and
`GET /jobs/{id}/events?after_id=N`.

### Request IDs, logs, and rate limits

Every response includes `X-Request-ID`. A caller may supply its own value in
the same header; the API accepts it only when it matches
`[A-Za-z0-9._:-]{1,64}` and otherwise generates a `req_...` value.

The API writes one JSON object per request to stderr. Records include
`request_id`, method, path, status, duration, client address, owner, and job ID
when known; authorization headers, query strings, request bodies, and file
contents are never logged. Set `LOG_LEVEL` to change verbosity.

Authenticated public requests also consume a per-owner token bucket. The
default is 120 requests per minute with a full initial burst. Exceeding it
returns `429 rate_limit_exceeded` with a `Retry-After` header. Health checks and
the internal worker protocol are exempt. Set
`RATE_LIMIT_REQUESTS_PER_MINUTE=0` to disable the limiter.

Successful job create, claim, cancel, retry, and finish transitions, plus
retention deletion, append rows to the `audit_events` table in the same
transaction as the change. Authentication and rate-limit denials are written
only to the structured logs, so unauthenticated traffic cannot create database
load:

```bash
sqlite3 /srv/md-service/db/app.db \
  "SELECT created_at, action, outcome, target_id, request_id
     FROM audit_events ORDER BY id DESC LIMIT 20;"
```

## Internal worker protocol

Internal routes use `X-Worker-Token`, not the public bearer token, and are
hidden from the OpenAPI document:

```bash
WORKER_TOKEN=dev-worker-token
INTERNAL=http://127.0.0.1:8000/internal/v1

# Claim the oldest queued job.  204 means the queue is empty.
curl -s -H "X-Worker-Token: $WORKER_TOKEN" -H "Content-Type: application/json" \
  -d '{"worker_id":"gpu-0","gpu_uuid":"GPU-..."}' "$INTERNAL/jobs/claim"

# Every later mutation carries the run_token returned by claim.  A stale token
# receives 409 stale_run_token.
curl -s -H "X-Worker-Token: $WORKER_TOKEN" -H "Content-Type: application/json" \
  -d "{\"run_token\":\"$RUN_TOKEN\",\"phase\":\"simulating\",\"stage\":\"equil-01\",\"step\":100,\"total_steps\":10000}" \
  "$INTERNAL/jobs/$JOB_ID/progress"
```

Heartbeat extends the lease only when `worker_id`, `current_job_id`, and
`run_token` match the active job. The reaper fails a job with
`error_code = "worker_lost"` after the 60-second lease expires, or marks it
canceled if cancellation had already been requested.

## Tests

No GPU, OpenMM import, or network access is required:

```bash
cd service/api
../../.venv/bin/python -m pip install -r requirements-dev.txt
../../.venv/bin/python -m pytest -q

cd ../worker
../../.venv/bin/python -m pytest -q
```

The API suite runs the real Alembic migration into a temporary SQLite database
and checks pragmas, generated TOML through `config.load_config()`, upload
limits, authentication, job creation, stage names, dry validation, ownership
filtering, worker claim/progress/finish flow, stale-token fencing,
cancellation, retry, queue ordering, artifact confinement, the lease reaper,
artifact/log downloads, SSE resume and terminal closure, queue and disk
admission limits, retention cleanup, request IDs, rate limiting, the audit
trail, docs policy, and a SQLite backup/restore round trip.

It also includes the contract tests, which run `scripts/check-contract.py`
over the whole service tree and confirm that it detects a deliberately
drifted value.

The worker suite uses a fake API client and a fake process handle. It checks the
fixed command, restart flags, stale-manifest clearing before a retry,
stdout/stderr capture, process-group signaling, progress parsing and throttling,
stage reconciliation, artifact classification and symlink rejection,
cancellation escalation, shutdown, stale-token handling, and unsafe claim-path
rejection.

The simulation suite also covers the progress writer, lifecycle and terminal
progress states, bounded chunked stepping, checkpoint preservation on
interruption, and the SIGTERM handler.

## Operations

New jobs are rejected with `429 queue_limit_exceeded` when the owner already has
`MAX_QUEUED_JOBS_PER_OWNER` queued jobs. Job creation also requires
`MIN_FREE_DISK_BYTES` of free space on `DATA_ROOT`; otherwise it returns
`507 insufficient_storage`. These checks never delete existing data.

Retention is opt-in. `RETENTION_DAYS=0` keeps every job and artifact. When set,
the cleanup task removes terminal jobs older than the window together with their
SQLite rows and job workspace. Audit rows are intentionally retained. It also
removes abandoned `users/*/jobs/.<id>.tmp` directories and
`users/*/uploads/**/*.part` files older than `ORPHAN_WORKSPACE_HOURS`. Run a
dry run first, preferably while the API and worker are idle:

```bash
cd service/api
export DATABASE_URL=sqlite:////srv/md-service/db/app.db
export DATA_ROOT=/srv/md-service/data
export RETENTION_DAYS=30

../../.venv/bin/python -m app.cleanup --dry-run
../../.venv/bin/python -m app.cleanup
```

The JSON report lists expired jobs, freed bytes, and orphan workspaces. In
Compose, run the same command inside the API image with the `/db` and `/data`
mounts:

```bash
docker compose run --rm --no-deps api python -m app.cleanup --dry-run
```

## Backup and restore

SQLite and job artifacts are separate backup units. Do not copy a live
`app.db` by itself; use SQLite's backup API or Litestream so WAL state is
included.

`scripts/backup.sh` does both of steps 2 and 3, and is scheduled by the
`md-backup.timer` user unit. Run it by hand with:

```bash
cd service
./scripts/backup.sh
```

To do it by hand instead:

1. Quiesce writers: stop the worker, then the API (`docker compose stop worker api`).
2. Back up the database:

   ```bash
   mkdir -p /srv/md-service/backups
   sqlite3 /srv/md-service/db/app.db \
     ".backup '/srv/md-service/backups/app-$(date +%Y%m%dT%H%M%S).db'"
   ```

3. Snapshot job data separately:

   ```bash
   tar -C /srv/md-service -czf \
     "/srv/md-service/backups/data-$(date +%Y%m%dT%H%M%S).tgz" data
   ```

4. Restore into a clean host directory:

   ```bash
   docker compose down
   cp /srv/md-service/backups/app-<timestamp>.db /srv/md-service/db/app.db
   rm -rf /srv/md-service/data/users /srv/md-service/data/cache
   tar -C /srv/md-service -xzf /srv/md-service/backups/data-<timestamp>.tgz
   chown -R 10001:10001 /srv/md-service/db /srv/md-service/data
   ```

5. Start `migrate`, then the API and worker; verify `/readyz`, a completed job's
   artifact download, and a queued job's presence before accepting new work.

The test suite performs the same sequence in a temporary directory: it uses
`sqlite3.Connection.backup`, copies the data root, reopens the restored
database, checks `PRAGMA integrity_check`, verifies job/stage/artifact rows,
and confirms the restored artifact files are readable.

## Security checklist

- Authentication uses constant-time comparisons. The public bearer token and
  the worker token are separate, and Caddy answers `/internal/*` with 404.
- Every account's password is stored only as a scrypt hash, never in
  plaintext. `set-admin-password.sh` writes the hash and removes the
  plaintext from `.env`; the hash is single-quoted so compose does not
  interpolate its `$` separators.
- Sign-in and registration are rate limited per client address, and every
  authenticated request is rate limited per account.
- Each account's data lives under `DATA_ROOT/users/<owner_id>/`, and every
  route that reads or writes a row checks the caller against its `owner_id`.
  The account id is part of the path, so a routing mistake cannot reach
  another account's files either.
- Request models use `extra="forbid"`. The public API accepts no raw TOML,
  filesystem path, executable, force-field path, platform, or platform
  property.
- The worker command is fixed and restart flags come from an enum. The API
  never imports OpenMM or creates a GPU context.
- Uploads stream to disk, hash while reading, enforce per-file and per-job
  limits, and accept only the documented suffixes. They also count the atoms
  in the structure and reject one over `MAX_UPLOAD_ATOMS`, because the
  simulation cost grows with the atom count and a byte limit does not bound
  the GPU time.
- PDB mode permits only a four-character ID and one fixed RCSB URL; it can be
  disabled with `ALLOW_PDB_DOWNLOAD=false`.
- Every file, job, artifact, log, and event stream is checked against the
  caller. Artifact and log downloads resolve by ID or fixed name only.
- Path handling rejects absolute paths, `.` and `..`, NUL bytes, escapes, and
  symlinks at every component.
- Every container that touches user-supplied structures runs unprivileged:
  the API, the worker and the prep worker all run as the contract service
  account with `cap_drop: [ALL]` and `no-new-privileges`. The API also has a
  read-only root filesystem. The worker keeps network access because it polls
  the API for jobs; the simulation itself reaches nothing.
- Compose mounts only `/db` and `/data`; there is no Docker socket. The
  worker mounts only `/data`.
- CORS is limited to `CORS_ORIGINS`, docs can be disabled with
  `DOCS_ENABLED=false`, and queue/rate limits bound public work.
- Request IDs and structured logs avoid tokens, query strings, and bodies.
  Accepted mutations append to `audit_events`.
- No `GET` handler changes state. The ones that write do so only to
  regenerate an idempotent derived cache.

## Configuration policy

Users may set only the values in `app/schemas.py`. The API always writes:

- `run.platform` from `SIMULATION_PLATFORM`;
- `run.output_dir` inside the job workspace;
- `parameterization.forcefields` and `ligand_forcefield`;
- `parameterization.ccd_cache` under `DATA_ROOT/cache/ccd`;
- generated stage names and resolved integer step counts.

`config.load_config()` is the final validation gate for every generated file.
A failure there is treated as a server bug, not a user error.

## Data layout

Every account owns its own tree, and the account id is part of the path as
well as part of every database row. A mistake in an ownership check therefore
cannot reach another account's files.

```text
DATA_ROOT/
├── users/<owner_id>/
│   ├── uploads/<file_id>/<safe-name>
│   ├── jobs/<job_id>/
│   │   ├── config.toml
│   │   ├── job.json
│   │   ├── inputs/
│   │   ├── logs/
│   │   └── outputs/            # created by simulate.py
│   └── prep/<prep_job_id>/     # preparation workspaces
└── cache/ccd/
```

The database stores only paths relative to `DATA_ROOT`. The worker mounts only
`DATA_ROOT`; the API is the only process that opens SQLite.

Before accounts existed the tree was flat (`uploads/`, `jobs/`, `prep/`).
`scripts/migrate_user_data.py` moves it into the per-account layout and
rewrites the stored keys to match.

## Migrations

Alembic is the only schema writer. The Compose `migrate` service runs
`alembic upgrade head` before the API and worker start. For manual operation:

```bash
cd service/api
DATABASE_URL=sqlite:////srv/md-service/db/app.db alembic upgrade head
```

Do not create tables at API startup and do not run multiple Uvicorn workers
against SQLite.
