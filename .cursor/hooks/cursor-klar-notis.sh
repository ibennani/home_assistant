#!/usr/bin/env bash
# Skickar mobilnotis till Elias S23 Ultra när en Cursor-agent är klar.
# Anropas av .cursor/hooks.json (afterAgentResponse + stop).

set -uo pipefail

MODE="${1:-stop}"
STATE_DIR=".cursor/hooks/state"
STATE_FILE="${STATE_DIR}/last-response.txt"

mkdir -p "$STATE_DIR"

load_env_value() {
  local key="$1"
  local value="${!key:-}"
  if [[ -n "$value" ]]; then
    printf '%s' "$value"
    return 0
  fi
  if [[ -f .env ]]; then
    value="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
    if [[ -n "$value" ]]; then
      printf '%s' "$value"
      return 0
    fi
  fi
  return 1
}

resolve_ha_url() {
  local ha_url mcp_url
  ha_url="$(load_env_value HA_URL || true)"
  if [[ -n "${ha_url:-}" ]]; then
    printf '%s' "$ha_url"
    return 0
  fi

  mcp_url="$(load_env_value HA_MCP_WEBHOOK_URL || true)"
  if [[ -n "${mcp_url:-}" ]]; then
    ha_url="${mcp_url%/api/webhook/mcp_*}"
    if [[ "$ha_url" != "$mcp_url" && -n "$ha_url" ]]; then
      printf '%s' "$ha_url"
      return 0
    fi
  fi

  return 1
}

save_last_response() {
  python3 - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
raw = sys.stdin.read()
if not raw.strip():
    sys.exit(0)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

text = (data.get("text") or "").strip()
if not text:
    sys.exit(0)

state_file.parent.mkdir(parents=True, exist_ok=True)
state_file.write_text(text, encoding="utf-8")
PY
}

extract_beskrivning() {
  python3 - "$STATE_FILE" <<'PY'
import re
import sys
from pathlib import Path

state_file = Path(sys.argv[1])
fallback = "Öppna Cursor och läs senaste svaret."

if not state_file.exists():
    print(fallback)
    raise SystemExit(0)

text = state_file.read_text(encoding="utf-8", errors="replace").strip()
if not text:
    print(fallback)
    raise SystemExit(0)

text = re.sub(r"```.*?```", " ", text, flags=re.S)
text = re.sub(r"\s+", " ", text).strip()

match = re.match(r"^(.{1,220}?[.!?])(?:\s|$)", text)
if match:
    print(match.group(1))
else:
    print(text[:200])
PY
}

send_notis() {
  local beskrivning="$1"
  local ha_url ha_token payload

  ha_url="$(resolve_ha_url || true)"
  if [[ -z "${ha_url:-}" ]]; then
    echo "[cursor-klar-notis] HA_URL saknas — ingen notis skickad." >&2
    return 0
  fi

  ha_token="$(load_env_value HA_TOKEN || true)"
  payload="$(BESKRIVNING="$beskrivning" python3 - <<'PY'
import json
import os

print(json.dumps({"beskrivning": os.environ["BESKRIVNING"]}, ensure_ascii=False))
PY
)"

  if [[ -n "${ha_token:-}" ]]; then
    curl -sfS -m 20 -X POST "${ha_url%/}/api/events/cursor_agent_klar" \
      -H "Authorization: Bearer ${ha_token}" \
      -H "Content-Type: application/json" \
      -d "$payload" >/dev/null 2>&1 && return 0
  fi

  curl -sfS -m 20 -X POST "${ha_url%/}/api/webhook/cursor_task_notification_ilias" \
    -H "Content-Type: application/json" \
    -d "$payload" >/dev/null 2>&1 || {
      echo "[cursor-klar-notis] Kunde inte skicka notis till Home Assistant." >&2
    }
}

case "$MODE" in
  after-response)
    save_last_response
    ;;
  stop)
    INPUT="$(cat)"
    STATUS="$(INPUT="$INPUT" python3 - <<'PY'
import json
import os

try:
    data = json.loads(os.environ.get("INPUT", "{}"))
except json.JSONDecodeError:
    data = {}

print(data.get("status", "completed"))
PY
)"
    if [[ "$STATUS" != "completed" ]]; then
      exit 0
    fi
    BESKRIVNING="$(extract_beskrivning)"
    send_notis "$BESKRIVNING"
    ;;
  *)
    ;;
esac

exit 0
