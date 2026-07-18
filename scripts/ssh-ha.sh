#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

HOST="${HA_SSH_HOST:-homeassistant.local}"
USER="${HA_SSH_USER:-root}"
PORT="${HA_SSH_PORT:-22}"

exec ssh -p "$PORT" "${USER}@${HOST}" "$@"
