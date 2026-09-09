#!/bin/bash
# Z-Wave JS UI migration: kopierar store, skriver settings.json, patchar integration.
# Loggar till /config/zwave-migrate.log och system_log (sök ZWAVE_MIGRATE).
set -uo pipefail

LOG=/config/zwave-migrate.log
: > "$LOG"
exec >> "$LOG" 2>&1

log_ha() {
  local msg="$1"
  echo "$msg"
  if [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
    curl -sS -X POST \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      -H "Content-Type: application/json" \
      "http://supervisor/core/api/services/system_log/write" \
      -d "{\"message\":\"ZWAVE_MIGRATE: ${msg}\",\"level\":\"warning\"}" >/dev/null 2>&1 || true
  fi
}

write_settings() {
  local dest="$1"
  cat > "$dest" << 'EOF'
{
  "gateway": {"type": 0, "payloadType": 0, "hassDiscovery": false, "logEnabled": true, "logLevel": "info", "logToFile": false, "nodeNames": true},
  "mqtt": {"auth": true, "disabled": true, "host": "core-mosquitto", "name": "Mosquitto", "password": "", "port": 1883, "username": ""},
  "zwave": {
    "commandsTimeout": 30, "logLevel": "info", "logToFile": false,
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
    "serverEnabled": true, "serverPort": 3000, "enableSoftReset": "auto", "rf": {"region": "auto"}
  }
}
EOF
}

log_ha "start $(date -Iseconds)"

CORE=/addon_configs/core_zwave_js
SLUG=a0d7b954_zwavejs2mqtt
ENTRY_ID=bddd840684d182ad003d4c0bb4bbca0e
SERIAL=/dev/serial/by-id/usb-0658_0200-if00

# Stoppa core och bryt eventuell stickkonflikt
ha addons stop core_zwave_js 2>&1 || true
ha addons options core_zwave_js --boot manual 2>/dev/null || true

# Stoppa UI (bryt crash-loop) innan vi skriver store
ha addons stop "$SLUG" 2>&1 || true
sleep 3

# Hitta persistent store-sökväg (supervisor data-volym)
STORE=""
for candidate in \
  "/mnt/data/supervisor/addons/data/${SLUG}/store" \
  "/addons/data/${SLUG}/store" \
  "/data/addons/data/${SLUG}/store"; do
  parent="$(dirname "$candidate")"
  if [[ -d "$parent" ]] || mkdir -p "$parent" 2>/dev/null; then
    mkdir -p "$candidate"
    STORE="$candidate"
    log_ha "store path $STORE"
    break
  fi
done

if [[ -z "$STORE" ]]; then
  log_ha "WARN no supervisor store path, falling back to docker exec"
fi

DB=""
if [[ -n "$STORE" ]]; then
  DB="$(dirname "$STORE")/db"
  mkdir -p "$DB"
fi

copied=0
if [[ -n "$STORE" ]]; then
  for f in nodes.json users.json scenes.json groups.json; do
    for src in "$CORE/$f" "$CORE/store/$f"; do
      if [[ -f "$src" ]]; then
        cp -f "$src" "$STORE/$f"
        log_ha "copied $f to store $(wc -c < "$src") bytes"
        copied=1
        break
      fi
    done
  done
  [[ -d "$CORE/.config-db" ]] && cp -a "$CORE/.config-db/." "$DB/" && log_ha "copied config-db to $DB"
  write_settings "$STORE/settings.json"
  log_ha "wrote settings.json to $STORE"
  ls -la "$STORE" 2>&1 | tr '\n' ' | ' | log_ha "store listing:"
fi

# Fallback: docker exec om supervisor-sökväg saknades eller nodes.json inte kopierades
if [[ $copied -eq 0 ]] && command -v docker >/dev/null 2>&1; then
  log_ha "docker fallback"
  ha addons start "$SLUG" 2>&1 || true
  sleep 8
  CID=$(docker ps --format '{{.Names}} {{.ID}}' | awk '/zwavejs2mqtt/ {print $2; exit}')
  if [[ -n "$CID" ]]; then
    log_ha "container $CID"
    docker exec "$CID" mkdir -p /data/store /data/db
    for f in nodes.json users.json scenes.json groups.json; do
      for src in "$CORE/$f" "$CORE/store/$f"; do
        if [[ -f "$src" ]]; then
          docker cp "$src" "$CID:/data/store/$f"
          log_ha "docker copied $f"
          copied=1
          break
        fi
      done
    done
    [[ -d "$CORE/.config-db" ]] && docker cp "$CORE/.config-db/." "$CID:/data/db/"
    write_settings /tmp/zwave-settings.json.$$
    docker cp /tmp/zwave-settings.json.$$ "$CID:/data/store/settings.json"
    rm -f /tmp/zwave-settings.json.$$
    ha addons stop "$SLUG" 2>&1 || true
    sleep 2
  else
    log_ha "ERROR no zwavejs2mqtt container for docker fallback"
  fi
fi

[[ $copied -eq 1 ]] || log_ha "WARN no nodes.json source in $CORE"

# Patcha integration till UI-websocket
python3 - << PY
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
print("patched config entry")
PY

log_ha "starting UI addon"
ha addons start "$SLUG" 2>&1 || true
sleep 40

if command -v docker >/dev/null 2>&1; then
  CID=$(docker ps --format '{{.Names}} {{.ID}}' | awk '/zwavejs2mqtt/ {print $2; exit}')
  if [[ -n "$CID" ]]; then
    serial_list=$(docker exec "$CID" ls /dev/serial/by-id/ 2>&1 | tr '\n' ' ' || echo none)
    log_ha "serial in container: $serial_list"
    store_list=$(docker exec "$CID" ls -la /data/store/ 2>&1 | tr '\n' ' | ')
    log_ha "container store: $store_list"
    driver_log=$(docker exec "$CID" sh -c 'grep -E "driver|Z-WAVE|port|listening" /tmp/log/*.log 2>/dev/null | tail -5' 2>&1 | tr '\n' ' ')
    log_ha "driver hints: $driver_log"
  else
    log_ha "WARN UI container not running after start"
  fi
fi

tail_log=$(ha addons logs "$SLUG" 2>&1 | tail -20 | tr '\n' ' ')
log_ha "UI log tail: $tail_log"
log_ha "done"
