#!/usr/bin/env bash
# Create the CPU-only ligand parameterization environment used by prepare_system.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PREFIX="${1:-$ROOT/.param-env}"

if [ -n "${MAMBA:-}" ] && [ -x "$MAMBA" ]; then
    :
elif command -v micromamba >/dev/null 2>&1; then
    MAMBA="$(command -v micromamba)"
elif [ -x "$ROOT/.tools/bin/micromamba" ]; then
    MAMBA="$ROOT/.tools/bin/micromamba"
else
    echo "micromamba was not found. Install micromamba or run this script with MAMBA=/path/to/micromamba." >&2
    exit 1
fi

export MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$ROOT/.mamba}"
"$MAMBA" create -y -p "$ENV_PREFIX" -f "$ROOT/environment-param.yml"
"$MAMBA" clean --all --yes

echo
echo "Parameterization environment created at: $ENV_PREFIX"
echo "Python: $ENV_PREFIX/bin/python"
