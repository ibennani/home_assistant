#!/bin/bash
# Tilldela USB till Z-Wave JS UI, skriv settings.json, starta UI.
# Körs från SSH-addon init_commands (har docker + supervisor).
set -uo pipefail

LOG=/config/zwave-usb-fix.log
: > "$LOG"
exec >> "$LOG" 2>&1

log_ha() {
  local msg="$1"
  echo "$(date -Iseconds) $msg"
  if [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
    curl -sf -X POST \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      -H "Content-Type: application/json" \
      "http://supervisor/core/api/services/system_log/write" \
      -d "{\"message\":\"ZWAVE_USB: ${msg}\",\"level\":\"warning\"}" >/dev/null 2>&1 || true
  fi
}

SLUG=a0d7b954_zwavejs2mqtt
# RFXCOM = ttyUSB0 — använd INTE. Z-Wave FTDI = ttyUSB1 på denna installation.
SERIAL_BY_ID=/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DM00ZRYW-if00-port0
SERIAL=/dev/ttyUSB1
UI_DATA=/mnt/data/supervisor/addons/data/${SLUG}
CORE_DATA=/mnt/data/supervisor/addons/data/core_zwave_js

log_ha "start"

# Stoppa core om den finns — starta ALDRIG core
ha addons stop core_zwave_js 2>/dev/null || true
if [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
  curl -sf -X POST \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    "http://supervisor/addons/core_zwave_js/options" \
    -d '{"boot":"manual","devices":[]}' 2>/dev/null || true
fi

# Tilldela USB till UI (addons.json + Supervisor API)
assign_usb() {
  if [[ -f /config/scripts/patch-zwave-usb.py ]]; then
    python3 /config/scripts/patch-zwave-usb.py 2>&1 | tee -a "$LOG" || true
    log_ha "patch-zwave-usb.py körd"
  fi
  if [[ -n "${SUPERVISOR_TOKEN:-}" ]]; then
    local resp body dev
    dev="$SERIAL_BY_ID"
    [[ -e "$dev" ]] || dev="$SERIAL"
    body=$(printf '{"devices":["%s"],"boot":"auto","options":{}}' "$dev")
    resp=$(curl -sS -w '%{http_code}' -o /tmp/zwave_usb_resp.txt -X POST \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      -H "Content-Type: application/json" \
      "http://supervisor/addons/${SLUG}/options" \
      -d "$body" 2>&1) || resp="000"
    log_ha "supervisor assign USB http=${resp} dev=${dev} body=$(head -c 200 /tmp/zwave_usb_resp.txt 2>/dev/null || echo none)"
    [[ "$resp" == "200" ]] && return 0
  fi
  log_ha "WARN USB kunde ej tilldelas via Supervisor API"
}
assign_usb

# Skriv settings + kopiera store
mkdir -p "${UI_DATA}/store"
for f in nodes.json users.json scenes.json groups.json; do
  for src in "${CORE_DATA}/store/${f}" "${CORE_DATA}/${f}"; do
    if [[ -f "$src" ]]; then
      cp "$src" "${UI_DATA}/store/${f}"
      log_ha "copied $f from $src"
      break
    fi
  done
done

cat > "${UI_DATA}/store/settings.json" << 'EOF'
{
  "gateway": {"type": 0, "payloadType": 0, "hassDiscovery": false, "logEnabled": true, "logLevel": "info", "logToFile": false, "nodeNames": true},
  "mqtt": {"auth": true, "disabled": true, "host": "core-mosquitto", "name": "Mosquitto", "password": "", "port": 1883, "username": ""},
  "zwave": {
    "commandsTimeout": 30, "logLevel": "info", "logToFile": false,
    "port": "/dev/ttyUSB1",
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
log_ha "wrote settings.json"
ls -la "${UI_DATA}/store/" 2>&1 | head -10

ha addons restart "${SLUG}" 2>&1 || ha addons start "${SLUG}" 2>&1 || true
log_ha "restarted UI"
log_ha "done"
