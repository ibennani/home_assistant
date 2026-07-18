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

ha_require_env() {
    if [[ -z "${HA_URL:-}" ]]; then
        echo "Fel: HA_URL saknas. Kopiera .env.example till .env." >&2
        exit 1
    fi
    if [[ -z "${HA_TOKEN:-}" ]]; then
        echo "Fel: HA_TOKEN saknas. Skapa long-lived token i Home Assistant." >&2
        exit 1
    fi
}

ha_api() {
    local method="${1:-GET}"
    local path="$2"
    shift 2 || true
    ha_require_env
    curl -sS -X "$method" \
        -H "Authorization: Bearer $HA_TOKEN" \
        -H "Content-Type: application/json" \
        "$HA_URL$path" "$@"
}
