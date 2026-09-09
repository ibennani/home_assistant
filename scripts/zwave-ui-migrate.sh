#!/bin/bash
# Z-Wave JS UI migration: copy store from core_zwave_js and configure stick/keys.
# Run on HA host via SSH addon: bash /config/scripts/zwave-ui-migrate.sh
set -euo pipefail

LOG=/config/zwave-migrate.log
exec > >(tee -a "$LOG") 2>&1

echo "=== zwave-ui-migrate $(date -Iseconds) ==="

CORE=/addon_configs/core_zwave_js
SLUG=a0d7b954_zwavejs2mqtt
PORT="/dev/serial/by-id/usb-0658_0200-if00"

UI=""
for BASE in \
  "/mnt/data/supervisor/addons/data/${SLUG}" \
  "/data/supervisor/addons/data/${SLUG}" \
  "/addon_configs/${SLUG}"; do
  if [[ -d "$BASE" ]]; then
    UI="$BASE"
    echo "UI data base: $BASE"
    break
  fi
done

if [[ -z "$UI" ]]; then
  echo "ERROR: Z-Wave JS UI addon data directory not found"
  exit 1
fi

mkdir -p "$UI/store" "$UI/db"

for f in nodes.json users.json scenes.json groups.json; do
  for src in "$CORE/$f" "$CORE/store/$f"; do
    if [[ -f "$src" ]]; then
      cp -a "$src" "$UI/store/$f"
      echo "copied $f from $src ($(wc -c < "$UI/store/$f") bytes)"
      break
    fi
  done
done

if [[ -d "$CORE/.config-db" ]]; then
  cp -a "$CORE/.config-db/." "$UI/db/"
  echo "copied .config-db"
fi

if [[ -d "$CORE/cache" ]]; then
  mkdir -p "$UI/store/cache"
  cp -a "$CORE/cache/." "$UI/store/cache/"
  echo "copied cache"
fi

cat > "$UI/store/settings.json" << 'EOF'
{
  "gateway": {
    "type": 0,
    "payloadType": 0,
    "hassDiscovery": false,
    "logEnabled": true,
    "logLevel": "info",
    "logToFile": false,
    "nodeNames": true
  },
  "mqtt": {
    "auth": true,
    "disabled": true,
    "host": "core-mosquitto",
    "name": "Mosquitto",
    "password": "",
    "port": 1883,
    "username": ""
  },
  "zwave": {
    "commandsTimeout": 30,
    "logLevel": "info",
    "logToFile": false,
    "port": "/dev/serial/by-id/usb-0658_0200-if00",
    "networkKey": "8603980F1A8F744FE709E464F636CC81",
    "securityKeys": {
      "S0_Legacy": "8603980F1A8F744FE709E464F636CC81",
      "S2_Unauthenticated": "080AEAF4855A7049E57674A6CC9FE67A",
      "S2_Authenticated": "D0BCDA897366765164F1640D6697C7D2",
      "S2_AccessControl": "7AC7BA1BBE9C6DCD22BDD91D2AC8C74C",
      "LR_S2_AccessControl": "44C9BD3BF95AE53BA46F40EFD785D523",
      "LR_S2_Authenticated": "0B4F89BC8AA5631CCC9C631428CF5930"
    },
    "serverEnabled": true,
    "serverPort": 3000,
    "enableSoftReset": "auto",
    "rf": { "region": "auto" }
  }
}
EOF

chmod 644 "$UI/store/settings.json"
echo "settings.json: $(wc -c < "$UI/store/settings.json") bytes"
ls -la "$UI/store/"

# Mirror to addon_configs (some HA versions)
mkdir -p "/addon_configs/${SLUG}/store" "/addon_configs/${SLUG}/db"
cp -a "$UI/store/." "/addon_configs/${SLUG}/store/"
cp -a "$UI/db/." "/addon_configs/${SLUG}/db/" 2>/dev/null || true

echo "Serial devices:"
ls -la /dev/serial/by-id/ 2>&1 || true

python3 - << 'PY'
import json
p = "/config/.storage/core.config_entries"
d = json.load(open(p))
for e in d["data"]["entries"]:
    if e.get("domain") == "zwave_js" and e.get("entry_id") == "bddd840684d182ad003d4c0bb4bbca0e":
        e["data"]["url"] = "ws://a0d7b954-zwavejs2mqtt:3000"
        e["data"]["use_addon"] = False
        e["data"]["integration_created_addon"] = False
        e["disabled_by"] = None
        e["state"] = "not_loaded"
        print("patched integration url ->", e["data"]["url"])
json.dump(d, open(p, "w"), indent=2)
PY

ha addons stop core_zwave_js || true
ha addons options core_zwave_js --boot manual 2>/dev/null || true
ha addons restart "$SLUG"
sleep 25
ha addons logs "$SLUG" | tail -40

echo "=== done ==="
