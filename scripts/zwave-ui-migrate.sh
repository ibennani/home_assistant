#!/bin/bash
# Z-Wave JS UI migration via docker exec (addon data is not under /addon_configs).
# Run from SSH addon context: bash /config/scripts/zwave-ui-migrate.sh
set -euo pipefail

LOG=/config/zwave-migrate.log
exec > >(tee -a "$LOG") 2>&1

echo "=== zwave-ui-migrate $(date -Iseconds) ==="

CORE=/addon_configs/core_zwave_js
SLUG=a0d7b954_zwavejs2mqtt
PORT="/dev/serial/by-id/usb-0658_0200-if00"

ha addons stop core_zwave_js 2>&1 || true

CID=""
for name in $(docker ps --format '{{.Names}}' 2>/dev/null); do
  if echo "$name" | grep -qi "zwavejs2mqtt"; then
    CID=$(docker ps --filter "name=$name" --format '{{.ID}}' | head -1)
    echo "Found container: $name ($CID)"
    break
  fi
done

if [[ -z "$CID" ]]; then
  echo "ERROR: Z-Wave JS UI container not running"
  ha addons start "$SLUG" 2>&1 || true
  sleep 10
  CID=$(docker ps --format '{{.Names}} {{.ID}}' | awk '/zwavejs2mqtt/ {print $2; exit}')
fi

if [[ -z "$CID" ]]; then
  echo "ERROR: still no container"
  exit 1
fi

echo "=== container store before ==="
docker exec "$CID" ls -la /data/store/ 2>&1 || true

docker exec "$CID" mkdir -p /data/store /data/db

for f in nodes.json users.json scenes.json groups.json; do
  for src in "$CORE/$f" "$CORE/store/$f"; do
    if [[ -f "$src" ]]; then
      docker cp "$src" "$CID:/data/store/$f"
      echo "docker cp $f from $src ($(wc -c < "$src") bytes)"
      break
    fi
  done
done

if [[ -d "$CORE/.config-db" ]]; then
  docker cp "$CORE/.config-db/." "$CID:/data/db/"
  echo "docker cp .config-db"
fi

if [[ -d "$CORE/cache" ]]; then
  docker exec "$CID" mkdir -p /data/store/cache
  docker cp "$CORE/cache/." "$CID:/data/store/cache/"
  echo "docker cp cache"
fi

docker exec -i "$CID" tee /data/store/settings.json > /dev/null << 'EOF'
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

echo "=== container store after ==="
docker exec "$CID" ls -la /data/store/
docker exec "$CID" head -c 200 /data/store/settings.json || true
echo
echo "=== serial in container ==="
docker exec "$CID" ls -la /dev/serial/by-id/ 2>&1 | head -10 || true

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
        print("patched url ->", e["data"]["url"])
json.dump(d, open(p, "w"), indent=2)
PY

ha addons stop core_zwave_js 2>&1 || true
ha addons restart "$SLUG"
sleep 30
ha addons logs "$SLUG" 2>&1 | tail -50

echo "=== done ==="
