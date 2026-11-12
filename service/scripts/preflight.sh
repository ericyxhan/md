#!/usr/bin/env bash
# Verify the deployment before it is started or published.
#
# Three layers of check:
#
#   1. The contract: every copy of a shared value still agrees.
#   2. The host: the paths, ports and accounts the deployment depends on.
#   3. The running stack: the containers, the edge and the public tunnel.
#
# The third layer is skipped when the stack is not running, so the script is
# also useful as a pre-flight check before the first launch.
#
# Usage:
#   ./preflight.sh
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/00-env.sh"

FAILURES=0

pass() { echo "[PASS] $1"; }
fail() {
    echo "[FAIL] $1"
    if [[ -n "${2:-}" ]]; then
        echo "       $2"
    fi
    FAILURES=$((FAILURES + 1))
}

echo "=== 1. shared contract ==="
if python3 "$SCRIPT_DIR/check-contract.py" >/tmp/md-contract-check.log 2>&1; then
    pass "every copy of a shared value agrees"
else
    fail "the shared values have drifted apart" \
         "run: python3 service/scripts/check-contract.py"
    grep -A2 "^\[FAIL\]" /tmp/md-contract-check.log | head -30
fi

echo
echo "=== 2. host ==="

if [[ -f "$ENV_FILE" ]]; then
    pass "the deployment env file exists"
else
    fail "the deployment env file is missing" "$ENV_FILE"
fi

HOST_DB_DIR="$(read_env HOST_DB_DIR /srv/md-service/db)"
HOST_DATA_DIR="$(read_env HOST_DATA_DIR /srv/md-service/data)"
MIN_FREE_DISK_BYTES="$(read_env MIN_FREE_DISK_BYTES 536870912)"

for key in SERVICE_API_TOKEN WORKER_TOKEN; do
    value="$(read_env "$key")"
    if [[ -z "$value" ]]; then
        fail "$key is not set" "the API refuses to start without it"
        continue
    fi
    if [[ ${#value} -lt 32 ]]; then
        fail "$key is too short" \
             "it is ${#value} characters; use at least 32"
    elif [[ "$value" == "test-service-token" || "$value" == "test-worker-token" ]]; then
        fail "$key is still the value from the test suite" \
             "rotate it: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'"
    else
        pass "$key is set and is not a default"
    fi
done

service_token="$(read_env SERVICE_API_TOKEN)"
worker_token="$(read_env WORKER_TOKEN)"
if [[ -n "$service_token" && "$service_token" == "$worker_token" ]]; then
    fail "SERVICE_API_TOKEN and WORKER_TOKEN are the same value" \
         "a leaked public token would then be a leaked worker token"
else
    pass "the public and worker tokens are different"
fi

if [[ -n "$(read_env WEB_PASSWORD)$(read_env WEB_PASSWORD_HASH)" ]]; then
    pass "a browser login is configured"
else
    fail "no browser login is configured" \
         "set WEB_PASSWORD_HASH in $ENV_FILE or the console cannot be opened"
fi

env_perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo "")"
if [[ "$env_perms" == "600" ]]; then
    pass "the env file is not readable by other accounts"
else
    fail "the env file is readable by other accounts" \
         "expected mode 600, found ${env_perms:-unknown}"
fi

if [[ -d "$HOST_DB_DIR" ]]; then
    pass "the database directory exists"
else
    fail "the database directory is missing" "$HOST_DB_DIR"
fi

if [[ -d "$HOST_DATA_DIR" ]]; then
    pass "the data directory exists"
    free_kb="$(df -Pk "$HOST_DATA_DIR" | awk 'NR==2 {print $4}')"
    if [[ "${free_kb:-0}" -ge $(( MIN_FREE_DISK_BYTES / 1024 )) ]]; then
        pass "the data directory has free space"
    else
        fail "the data directory is nearly full" \
             "$(( free_kb / 1024 )) MiB free, MIN_FREE_DISK_BYTES asks for $(( MIN_FREE_DISK_BYTES / 1024 )) MiB"
    fi
else
    fail "the data directory is missing" "$HOST_DATA_DIR"
fi

edge_bindings="$(ss -tlnH 2>/dev/null | awk -v p=":${MD_EDGE_PORT}\$" '$4 ~ p {print $4}')"
if [[ -z "$edge_bindings" ]]; then
    echo "[SKIP] the edge port is not listening yet"
elif echo "$edge_bindings" | grep -qvE '^(127\.0\.0\.1|\[::1\]):'; then
    fail "the edge port is published on all interfaces" \
         "it must be bound to 127.0.0.1 so only the tunnel can reach it; found: $(echo "$edge_bindings" | tr '\n' ' ')"
else
    pass "the edge port is bound to the loopback interface"
fi

echo
echo "=== 3. running stack ==="

STACK_RUNNING=false
if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -q "^api$"; then
    STACK_RUNNING=true
    pass "the stack is running"

    for service in api web worker prep-worker caddy; do
        if "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx "$service"; then
            pass "the $service container is running"
        else
            fail "the $service container is not running" "docker compose ps"
        fi
    done

    # A secret written unquoted into .env can be mangled by compose's
    # variable interpolation: a scrypt hash contains '$' separators, and an
    # unquoted value loses everything after the first one.  Compare the file
    # with what the running container actually received.
    env_hash="$(read_env WEB_PASSWORD_HASH)"
    if [[ -n "$env_hash" ]]; then
        container_hash="$(docker inspect md-service-api-1 \
            --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
            | sed -n 's/^WEB_PASSWORD_HASH=//p' | tail -n 1)"
        if [[ "$container_hash" == "$env_hash" ]]; then
            pass "the password hash reached the api intact"
        else
            fail "the password hash was altered on its way to the api" \
                 "the browser login will not work; quote the value in $ENV_FILE"
        fi
    fi

    # Every service that parses user-supplied files runs unprivileged.
    for service in worker prep-worker; do
        caps="$(docker inspect "md-service-$service-1" --format '{{.HostConfig.CapDrop}}' 2>/dev/null)"
        if [[ "$caps" == *ALL* ]]; then
            pass "the $service container has dropped all capabilities"
        else
            fail "the $service container still has capabilities" \
                 "expected CapDrop=[ALL], found ${caps:-unknown}"
        fi
    done

    if curl -sf --max-time 10 "http://127.0.0.1:${MD_EDGE_PORT}/healthz" >/dev/null; then
        pass "the edge answers on the contract port"
    else
        fail "the edge does not answer on the contract port" \
             "http://127.0.0.1:${MD_EDGE_PORT}/healthz"
    fi

    internal_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        "http://127.0.0.1:${MD_EDGE_PORT}${MD_INTERNAL_PREFIX}/jobs/claim" || true)"
    if [[ "$internal_code" == "404" ]]; then
        pass "worker routes are refused at the edge"
    else
        fail "worker routes are not refused at the edge" \
             "expected 404, got $internal_code"
    fi
else
    echo "[SKIP] the stack is not running"
fi

if [[ "$STACK_RUNNING" != "true" ]]; then
    echo "[SKIP] the public tunnel cannot be checked while the stack is down"
elif systemctl --user is-active --quiet md-funnel.service 2>/dev/null; then
    pass "the funnel service is running"
    public_url="$(journalctl --user -u md-funnel.service -n 20 --no-pager 2>/dev/null \
        | grep -oE 'https://[a-z0-9.-]+\.ts\.net' | tail -n 1)"
    if [[ -n "$public_url" ]]; then
        pass "the public URL is $public_url"
        code="$(curl -4 -s -o /dev/null -w '%{http_code}' --max-time 25 "$public_url/healthz" || true)"
        if [[ "$code" == "200" ]]; then
            pass "the public URL answers"
        else
            fail "the public URL does not answer" "got $code from $public_url/healthz"
        fi
    else
        fail "the public URL could not be determined" \
             "journalctl --user -u md-funnel.service"
    fi
else
    echo "[SKIP] the funnel service is not running"
fi

echo
if [[ "$FAILURES" -eq 0 ]]; then
    echo "Preflight passed."
    exit 0
fi
echo "Preflight failed with $FAILURES problem(s)."
exit 1
