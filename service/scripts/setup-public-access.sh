#!/usr/bin/env bash
# Publish the MD service to the internet through a Tailscale Funnel tunnel.
#
# The funnel terminates TLS and forwards to Caddy, which listens on plain HTTP
# on the loopback interface only.  The SPA and the API therefore share one
# origin, so the browser session cookie, the CSRF token, artifact downloads
# and the event stream all work without any cross-origin handling.
#
# Nothing listens on a public port: the funnel connects outward, so the host
# needs no public IP and no router configuration.
#
# This installs Tailscale into the user's home directory and runs it in
# userspace mode, so it needs no root.  Kernel mode is faster but requires
# CAP_NET_ADMIN; install the official package instead if you want it.
#
# Usage:
#   ./setup-public-access.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TAILSCALE_VERSION="1.104.6"
PKG_ROOT="$HOME/.local/share/tailscale-pkg"
STATE_DIR="$HOME/.local/share/tailscale"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

CONTRACT_FILE="$SERVICE_DIR/contract.env"
SOCKET="$STATE_DIR/tailscaled.sock"

if [[ ! -f "$CONTRACT_FILE" ]]; then
    echo "ERROR: contract file not found: $CONTRACT_FILE" >&2
    exit 1
fi

# The edge port comes from the contract, so the funnel target always matches
# the port Caddy listens on.
set -a
# shellcheck disable=SC1090
source "$CONTRACT_FILE"
set +a
FUNNEL_TARGET="http://127.0.0.1:${MD_EDGE_PORT}"

echo "==> Installing Tailscale $TAILSCALE_VERSION into $PKG_ROOT"
if [[ ! -x "$PKG_ROOT/usr/sbin/tailscaled" ]]; then
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/tailscale.deb" \
        "https://pkgs.tailscale.com/stable/tailscale_${TAILSCALE_VERSION}_amd64.deb"
    dpkg-deb -x "$tmp/tailscale.deb" "$PKG_ROOT"
    rm -rf "$tmp"
fi
mkdir -p "$BIN_DIR" "$STATE_DIR" "$UNIT_DIR"
ln -sf "$PKG_ROOT/usr/bin/tailscale" "$BIN_DIR/tailscale"
ln -sf "$PKG_ROOT/usr/sbin/tailscaled" "$BIN_DIR/tailscaled"
TAILSCALE_BIN="$BIN_DIR/tailscale"
"$TAILSCALE_BIN" version | head -1

echo
echo "==> Installing the user systemd units"
# The unit templates carry placeholders for paths that differ per host; fill
# them in here so the installed units never point at a stale location.
render_unit() {
    local template="$1" target="$2"
    sed -e "s#@@TAILSCALE_BIN@@#$TAILSCALE_BIN#g" \
        -e "s#@@CONTRACT_FILE@@#$CONTRACT_FILE#g" \
        -e "s#@@BACKUP_SCRIPT@@#$SCRIPT_DIR/backup.sh#g" \
        "$template" >"$target"
    chmod 0644 "$target"
}
render_unit "$SCRIPT_DIR/tailscaled.service" "$UNIT_DIR/tailscaled.service"
render_unit "$SCRIPT_DIR/md-funnel.service" "$UNIT_DIR/md-funnel.service"
render_unit "$SCRIPT_DIR/md-backup.service" "$UNIT_DIR/md-backup.service"
cp "$SCRIPT_DIR/md-backup.timer" "$UNIT_DIR/md-backup.timer"
chmod 0644 "$UNIT_DIR/md-backup.timer"

systemctl --user daemon-reload
systemctl --user enable tailscaled.service md-funnel.service md-backup.timer

echo
echo "==> Enabling linger so the services survive logout and reboot"
# Lets the units keep running without an active login session.
loginctl enable-linger "$(id -un)" 2>/dev/null \
    || echo "    could not enable linger; the services will stop when you log out"

echo
echo "==> Starting the Tailscale daemon"
systemctl --user restart tailscaled.service
sleep 5

if ! "$TAILSCALE_BIN" --socket="$SOCKET" status >/dev/null 2>&1; then
    echo "ERROR: the tailscaled service did not come up" >&2
    systemctl --user status tailscaled.service --no-pager || true
    exit 1
fi

if ! "$TAILSCALE_BIN" --socket="$SOCKET" status 2>&1 | grep -qE "^(100\.|fd7a:)"; then
    cat <<EOF

==> One step left: authenticate this host.

    $TAILSCALE_BIN --socket=$SOCKET up --accept-dns=false --ssh=false --hostname=\$(hostname -s)

It prints a login URL.  Open it, sign in, and the node joins your tailnet.
Then enable Funnel for the tailnet using the link the command prints.

EOF
    exit 0
fi

echo
echo "==> Starting the Funnel service"
systemctl --user restart md-funnel.service
sleep 5
journalctl --user -u md-funnel.service -n 10 --no-pager | grep -i "https://" || true

cat <<EOF

==> Done.  The public URL is in the output above.

    Verify it:
      curl -s -o /dev/null -w "%{http_code}\\n" https://<machine>.<tailnet>.ts.net/healthz

    Watch the services:
      systemctl --user status tailscaled.service md-funnel.service

EOF
