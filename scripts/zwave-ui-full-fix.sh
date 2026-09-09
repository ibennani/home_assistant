#!/bin/bash
# Full Z-Wave JS UI fix: USB (FTDI/ttyUSB1), settings, integration, omstart.
set -uo pipefail

LOG=/config/zwave-full-fix.log
: > "$LOG"
exec >> "$LOG" 2>&1

log_ha() {
  echo "$(date -Iseconds) $1"
  [[ -n "${SUPERVISOR_TOKEN:-}" ]] && curl -sf -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/core/api/services/system_log/write" \
    -d "{\"message\":\"ZWAVE_FIX: $1\",\"level\":\"warning\"}" >/dev/null 2>&1 || true
}

SLUG=a0d7b954_zwavejs2mqtt
ENTRY_ID=bddd840684d182ad003d4c0bb4bbca0e
DEV=/dev/ttyUSB1
DEV_ID=/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DM00ZRYW-if00-port0
UI_DATA=/mnt/data/supervisor/addons/data/${SLUG}
CORE_DATA=/mnt/data/supervisor/addons/data/core_zwave_js

log_ha "start"

ha apps stop core_zwave_js 2>&1 || true
ha apps stop "$SLUG" 2>&1 || true
sleep 3

# Patch addons.json direkt (Supervisor API ger HTTP 400)
for AJ in /mnt/data/supervisor/addons.json /data/addons.json; do
  [[ -f "$AJ" ]] || continue
  python3 - "$AJ" "$DEV_ID" <<'PY'
import json, sys
path, dev = sys.argv[1], sys.argv[2]
d = json.load(open(path))
e = d.setdefault("user", {}).setdefault("a0d7b954_zwavejs2mqtt", {})
e["devices"] = [dev]
e["boot"] = "auto"
json.dump(d, open(path, "w"), indent=2)
print(f"patched {path} devices={e['devices']}")
PY
  log_ha "addons.json patched via $AJ"
done

# Store + rensa gammal db (tvingar settings.json)
mkdir -p "${UI_DATA}/store"
rm -rf "${UI_DATA}/db" "${UI_DATA}/.config-db" 2>/dev/null || true

for src in /addon_configs/core_zwave_js/nodes.json \
  "${CORE_DATA}/store/nodes.json" "${CORE_DATA}/nodes.json"; do
  [[ -f "$src" ]] && cp -f "$src" "${UI_DATA}/store/nodes.json" && log_ha "nodes from $src ($(wc -c < "$src") bytes)" && break
done

cat > "${UI_DATA}/store/settings.json" <<EOF
{
  "gateway": {"type": 0, "payloadType": 0, "hassDiscovery": false, "logEnabled": true, "logLevel": "info", "logToFile": false, "nodeNames": true},
  "mqtt": {"auth": true, "disabled": true, "host": "core-mosquitto", "name": "Mosquitto", "password": "", "port": 1883, "username": ""},
  "zwave": {
    "commandsTimeout": 30, "logLevel": "info", "logToFile": false,
    "port": "${DEV}",
    "networkKey": "8603980F1A8F744FE709E464F636CC81",
    "securityKeys": {
      "S0_Legacy": "8603980F1A8F744FE709E464F636CC81",
      "S2_Unauthenticated": "080AEAF4855A7049E57674A6CC9FE67A",
      "S2_Authenticated": "D0BCDA897366765164F1640D6697C7D2",
      "S2_AccessControl": "7AC7BA1BBE9C6DCD22BDD91D2AC8C74C",
      "LR_S2_AccessControl": "44C9BD3BF95AE53BA46F40EFD785D523",
      "LR_S2_Authenticated": "0B4F89BC8AA5631CCC9C631428CF5930"
    },
    "serverEnabled": true, "serverPort": 3000, "enableSoftReset": "auto", "rf": {"region": "auto"}
  }
}
EOF
log_ha "settings port=${DEV} nodes=$(wc -c < "${UI_DATA}/store/nodes.json" 2>/dev/null || echo 0)"

# Patcha integration
python3 - <<PY
import json
p = "/config/.storage/core.config_entries"
d = json.load(open(p))
for e in d["data"]["entries"]:
    if e.get("domain") == "zwave_js" and e.get("entry_id") == "${ENTRY_ID}":
        e["data"]["url"] = "ws://a0d7b954-zwavejs2mqtt:3000"
        e["data"]["use_addon"] = False
        e["data"]["integration_created_addon"] = False
        e["disabled_by"] = None
json.dump(d, open(p, "w"), indent=2)
print("integration patched")
PY
log_ha "integration ws://a0d7b954-zwavejs2mqtt:3000"

ha apps start "$SLUG" 2>&1 || true
sleep 50

log_ha "UI state=$(ha apps info "$SLUG" 2>/dev/null | grep -o 'state: [^ ]*' || echo unknown)"
log_ha "done"
