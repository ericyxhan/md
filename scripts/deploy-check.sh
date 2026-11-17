#!/usr/bin/env bash
set -euo pipefail

echo "== MolDy deploy preflight (basic) =="
echo

ok() { echo "[OK] $*"; }
warn() { echo "[WARN] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker not found in PATH"
ok "docker found: $(docker --version 2>&1 | head -n1)"

if docker compose version >/dev/null 2>&1; then
  ok "docker compose found: $(docker compose version 2>&1 | head -n1)"
else
  fail "docker compose (v2) not found"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  ok "nvidia-smi found"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1 | sed 's/^/  GPU: /' || warn "could not query GPU details"
else
  warn "nvidia-smi not found (GPU may not be visible on this host)"
fi

echo
echo "Check these manually (common mistakes):"
echo "  - service/.env exists and has SERVICE_API_TOKEN, WORKER_TOKEN, WEB_SESSION_SECRET set"
echo "  - HOST_DATA_DIR/HOST_DB_DIR exist and are writable by uid 10001 (or match MD_SERVICE_UID)"
echo "  - Ports 8080 (Caddy) / 8000 internal not conflicting unexpectedly"
echo "  - After 'docker compose up', visit /healthz via your edge URL and sign in at /"
echo
echo "Done."
