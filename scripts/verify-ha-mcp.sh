#!/usr/bin/env bash
# Verifiera Home Assistant-anslutning (REST API + MCP-webhook).
# Linux/macOS/Cloud-motsvarighet till verify-ha-mcp.ps1.
#
# Kör: bash scripts/verify-ha-mcp.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Fallback: Cloud Agent-hemlighet där namnet = HA-URL och värdet = token.
if [[ -z "${HA_TOKEN:-}" ]]; then
    while IFS= read -r -d '' kv; do
        name="${kv%%=*}"
        val="${kv#*=}"
        if [[ "$name" =~ ^https://.*\.ui\.nabu\.casa/?$ ]]; then
            HA_URL="${HA_URL:-${name%/}}"
            HA_TOKEN="${HA_TOKEN:-$val}"
            break
        fi
    done < <(env -0)
fi

MCP_URL="${HA_MCP_WEBHOOK_URL:-}"
if [[ -z "$MCP_URL" && -f "$PROJECT_ROOT/.cursor/mcp.json" ]] && command -v jq >/dev/null 2>&1; then
    MCP_URL="$(jq -r '.mcpServers["home-assistant"].url // empty' "$PROJECT_ROOT/.cursor/mcp.json" 2>/dev/null)"
fi

mask_url() {
    local u="$1"
    [[ -z "$u" ]] && { echo "(saknas)"; return; }
    sed -E 's#(mcp_)[a-zA-Z0-9]+#\1****#; s#(://[^/]+).*#\1/…#' <<<"$u"
}

http_status() {
    local url="$1" token="${2:-}"
    if [[ -n "$token" ]]; then
        curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
            -H "Authorization: Bearer $token" "$url" 2>/dev/null || echo "000"
    else
        curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null || echo "000"
    fi
}

PASS=0
TOTAL=0
check() {
    local name="$1" got="$2" expected="$3" detail="${4:-}"
    TOTAL=$((TOTAL + 1))
    local ok="FAIL"
    for e in $expected; do
        if [[ "$got" == "$e" ]]; then ok="OK"; PASS=$((PASS + 1)); break; fi
    done
    printf '[%-4s] %s: HTTP %s (förväntat %s)%s\n' \
        "$ok" "$name" "$got" "${expected// / eller }" \
        "${detail:+ - $detail}"
}

echo "=== Home Assistant MCP-verifiering (bash) ==="
echo

if [[ -z "${HA_URL:-}" || -z "${HA_TOKEN:-}" ]]; then
    echo "[FAIL] HA_URL/HA_TOKEN saknas. Kopiera .env.example till .env och fyll i,"
    echo "       eller lägg till en hemlighet (namn = HA-URL, värde = token)."
    exit 1
fi

BASE="${HA_URL%/}"
echo "HA-URL:      $(mask_url "$BASE")"
echo "MCP-webhook: $(mask_url "$MCP_URL")"
echo

check "HA REST API (utan auth)" "$(http_status "$BASE/api/")" "401 403" "$BASE/api/"
check "HA REST API (med token)" "$(http_status "$BASE/api/" "$HA_TOKEN")" "200" "$BASE/api/"

if [[ -n "$MCP_URL" ]]; then
    check "MCP-webhook (Nabu Casa)" "$(http_status "$MCP_URL")" "405" "$(mask_url "$MCP_URL")"
else
    echo "[SKIP] MCP-webhook - ingen URL (sätt HA_MCP_WEBHOOK_URL eller .cursor/mcp.json)"
fi

echo
if [[ "$PASS" -eq "$TOTAL" ]]; then
    echo "=== Alla $TOTAL kontroller OK ==="
    echo
    echo "REST API fungerar. För MCP i Cloud Agent / Automation:"
    echo "  Lägg till 'home-assistant' (HTTP) på https://cursor.com/agents"
    echo "  Se docs/cursor-cloud-mcp-steg.md"
    exit 0
fi

echo "=== $PASS/$TOTAL kontroller OK ==="
exit 1
