#!/bin/bash
set -euo pipefail

BACKUP_ID="${1:-3f04bae7}"
OUT_DIR="${2:-/tmp/ha-recovery}"
BACKUP="/backup/${BACKUP_ID}.tar"
WORK="${OUT_DIR}/${BACKUP_ID}"

mkdir -p "$WORK"
cd "$WORK"

echo "=== Extracting homeassistant.tar.gz from ${BACKUP} ==="
python3 <<PY
import tarfile
from pathlib import Path

backup = Path("${BACKUP}")
work = Path("${WORK}")
with tarfile.open(backup, "r:") as outer:
    outer.extract("homeassistant.tar.gz", work)
print("outer ok")
PY

echo "=== Listing key yaml files in inner archive ==="
tar -tzf "$WORK/homeassistant.tar.gz" | grep -E '(automations|configuration|scripts|ui-lovelace|groups|input_|zone)\.yaml$' | head -20

echo "=== Extracting yaml files ==="
for f in automations.yaml configuration.yaml scripts.yaml ui-lovelace.yaml groups.yaml \
  input_boolean.yaml input_datetime.yaml input_number.yaml input_select.yaml input_text.yaml \
  zone.yaml scenes.yaml known_devices.yaml secrets.yaml; do
  tar -xzf "$WORK/homeassistant.tar.gz" -C "$WORK" "./$f" 2>/dev/null || tar -xzf "$WORK/homeassistant.tar.gz" -C "$WORK" "$f" 2>/dev/null || echo "skip $f"
done

echo "=== house_time_modes in backup automations.yaml ==="
grep -n "Huset: Styr house_time_modes" "$WORK/automations.yaml" || true
sed -n '/Huset: Styr house_time_modes/,/^- alias/p' "$WORK/automations.yaml" | head -25

echo "=== Line counts ==="
wc -l "$WORK"/*.yaml 2>/dev/null | tail -15

echo "=== DONE: $WORK ==="
