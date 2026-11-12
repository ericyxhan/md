#!/usr/bin/env bash
# Launch the caddy edge proxy.
#
# Routes /api/* and /healthz to the api container and serves the SPA for
# everything else.  Depends on api and web being healthy.
#
# Caddy listens on plain HTTP on the loopback interface: TLS is terminated by
# Tailscale Funnel in front of it, so it never requests a certificate itself.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

echo "[launch-caddy] starting caddy ..."
"${COMPOSE[@]}" up -d caddy

echo "[launch-caddy] caddy container status:"
"${COMPOSE[@]}" ps caddy
