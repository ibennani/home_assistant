#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

BLOCKED=('.env' 'secrets.yaml' '.storage' 'home-assistant_v2.db' '.pem' 'id_rsa' 'reports/')
STAGED="$(git diff --cached --name-only 2>/dev/null || true)"

if [[ -z "$STAGED" ]]; then
    echo "Inget staged."
    exit 0
fi

FAIL=0
while IFS= read -r file; do
    for pattern in "${BLOCKED[@]}"; do
        if [[ "$file" == *"$pattern"* ]]; then
            echo "BLOCKERAD: $file ($pattern)" >&2
            FAIL=1
        fi
    done
done <<< "$STAGED"

if [[ "$FAIL" -eq 1 ]]; then
    exit 1
fi
echo "Säkerhetskontroll OK."
