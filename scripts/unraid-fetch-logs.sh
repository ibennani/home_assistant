#!/usr/bin/env bash
# Hämtar diagnostik från Unraid via SSH (körs på HA-servern).
set -euo pipefail

HOST="${UNRAID_HOST:-192.168.0.234}"
USER="${UNRAID_USER:-root}"
PASS="${UNRAID_SSH_PASSWORD:-}"
OUT="${UNRAID_LOG_OUT:-/config/unraid-log-latest.txt}"

if [[ -z "$PASS" ]]; then
  echo "UNRAID_SSH_PASSWORD saknas (lägg till i secrets.yaml)." >&2
  exit 1
fi

export SSHPASS="$PASS"
REMOTE='
echo "=== uptime ==="
uptime
echo "=== last boot ==="
who -b 2>/dev/null || true
echo "=== syslog (senaste rader) ==="
if [[ -f /boot/logs/syslog ]]; then
  tail -n 1200 /boot/logs/syslog
elif [[ -f /var/log/syslog ]]; then
  tail -n 1200 /var/log/syslog
else
  echo "ingen syslog hittades"
fi
echo "=== dmesg (senaste) ==="
if dmesg -T >/dev/null 2>&1; then
  dmesg -T | tail -n 500
else
  dmesg | tail -n 500
fi
echo "=== docker status (kort) ==="
docker ps -a --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | head -50 || true
'

{
  echo "=== Unraid log snapshot $(date -Iseconds) ==="
  sshpass -e ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 "${USER}@${HOST}" "$REMOTE"
} 2>&1 | tee "$OUT"

echo "Saved to ${OUT}"
