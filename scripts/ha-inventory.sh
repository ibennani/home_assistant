#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/ha_api.sh"

PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$PROJECT_ROOT/reports"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_FILE="$REPORT_DIR/inventory-$TIMESTAMP.json"

mkdir -p "$REPORT_DIR"

echo "Hämtar inventering från $HA_URL ..."

CONFIG_JSON="$(ha_api GET /api/config)"
STATES_JSON="$(ha_api GET /api/states)"
SERVICES_JSON="$(ha_api GET /api/services)"

ADDONS_JSON="null"
if ha_api GET /api/hassio/addons 2>/dev/null | jq -e '.data.addons' >/dev/null 2>&1; then
    ADDONS_JSON="$(ha_api GET /api/hassio/addons)"
fi

jq -n \
    --argjson config "$CONFIG_JSON" \
    --argjson states "$STATES_JSON" \
    --argjson services "$SERVICES_JSON" \
    --argjson addons "$ADDONS_JSON" \
    '{
        generated_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
        homeassistant: {
            version: $config.version,
            location_name: $config.location_name,
            time_zone: $config.time_zone,
            components: ($config.components | sort),
            config_dir: $config.config_dir
        },
        entity_summary: (
            $states
            | group_by(.entity_id | split(".")[0])
            | map({domain: (.[0].entity_id | split(".")[0]), count: length})
            | sort_by(.domain)
        ),
        conversation_agents: (
            $states
            | map(select(.entity_id | startswith("conversation.")))
            | map({entity_id, state})
        ),
        addons: (
            if $addons == null then []
            else ($addons.data.addons | map({name, slug, state, version}))
            end
        )
    }' > "$REPORT_FILE"

echo ""
echo "Klar: $REPORT_FILE"
echo "Version: $(jq -r '.homeassistant.version' "$REPORT_FILE")"
echo "Komponenter: $(jq -r '.homeassistant.components | length' "$REPORT_FILE")"
echo "Tillägg: $(jq -r '.addons | length' "$REPORT_FILE")"

if jq -e '.homeassistant.components[] | select(. == "whatsapp")' "$REPORT_FILE" >/dev/null 2>&1; then
    echo "WhatsApp: installerad"
else
    echo "WhatsApp: saknas"
fi
