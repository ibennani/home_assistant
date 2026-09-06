#!/usr/bin/env bash
# Samlad verifiering före deploy / innan uppgiften markeras som klar.
# Kör: bash scripts/verify-change.sh [--staged]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

STAGED_ONLY=0
if [[ "${1:-}" == "--staged" ]]; then
    STAGED_ONLY=1
fi

PASS=0
TOTAL=0
FAIL=0

check_ok() {
    local name="$1"
    TOTAL=$((TOTAL + 1))
    PASS=$((PASS + 1))
    echo "[OK]   $name"
}

check_fail() {
    local name="$1"
    local detail="${2:-}"
    TOTAL=$((TOTAL + 1))
    FAIL=1
    echo "[FAIL] $name${detail:+ — $detail}" >&2
}

echo "=== verify-change ==="
echo

# 1. Säkerhet (staged om --staged, annars hoppa över om inget staged)
if [[ "$STAGED_ONLY" -eq 1 ]]; then
  if bash "$SCRIPT_DIR/pre-commit-check.sh"; then
    check_ok "Säkerhetskontroll (staged)"
  else
    check_fail "Säkerhetskontroll (staged)"
  fi
else
  echo "[SKIP] Säkerhetskontroll (kör med --staged före commit)"
fi

# 2. YAML-syntax
yaml_files=()
if [[ "$STAGED_ONLY" -eq 1 ]]; then
  mapfile -t yaml_files < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.(ya?ml)$' || true)
else
  while IFS= read -r -d '' f; do
    yaml_files+=("$f")
  done < <(find . -type f \( -name '*.yaml' -o -name '*.yml' \) \
    ! -path './.git/*' ! -path './reports/*' -print0 2>/dev/null)
fi

if [[ ${#yaml_files[@]} -eq 0 ]]; then
  echo "[SKIP] YAML-syntax (inga yaml-filer att kontrollera)"
else
  if python3 - "$PROJECT_ROOT" "${yaml_files[@]}" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML saknas — installera med: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def _ha_tag(loader, tag_suffix, node):
    """Acceptera HA-specifika taggar (!include, !secret, !input, …)."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


yaml.SafeLoader.add_multi_constructor("!", _ha_tag)

root = Path(sys.argv[1])
files = [Path(p) for p in sys.argv[2:]]
errors = 0
for path in files:
    rel = path if path.is_absolute() else root / path
    if not rel.is_file():
        continue
    try:
        list(yaml.safe_load_all(rel.read_text(encoding="utf-8")))
    except yaml.YAMLError as e:
        print(f"{rel}: {e}", file=sys.stderr)
        errors += 1
sys.exit(1 if errors else 0)
PY
  then
    check_ok "YAML-syntax (${#yaml_files[@]} filer)"
  else
    rc=$?
    if [[ "$rc" -eq 2 ]]; then
      echo "[SKIP] YAML-syntax (PyYAML ej installerat)"
    else
      check_fail "YAML-syntax"
    fi
  fi
fi

# 3. HA YAML-validering (state-triggers, duplicerade id, …)
ha_yaml_files=()
if [[ "$STAGED_ONLY" -eq 1 ]]; then
  for f in "${yaml_files[@]}"; do
    case "$f" in
      automations.yaml|scripts.yaml|*/automations.yaml|*/scripts.yaml)
        ha_yaml_files+=("$f")
        ;;
    esac
  done
else
  ha_yaml_files=("automations.yaml" "scripts.yaml")
fi

if [[ ${#ha_yaml_files[@]} -eq 0 ]]; then
  echo "[SKIP] HA YAML-validering (inga automations/scripts i kontrollen)"
elif python3 "$SCRIPT_DIR/check-ha-yaml.py" "${ha_yaml_files[@]}"; then
  check_ok "HA YAML-validering (${#ha_yaml_files[@]} filer)"
else
  check_fail "HA YAML-validering" "kör: python3 scripts/check-ha-yaml.py"
fi

# 4. config_check mot live HA (valfritt)
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/ha_api.sh" 2>/dev/null || true

if [[ -n "${HA_URL:-}" && -n "${HA_TOKEN:-}" ]]; then
  resp="$(ha_api POST /api/config/core/check_config -d '{}' 2>/dev/null || echo '{"result":"error"}')"
  if echo "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('result')=='valid' else 1)" 2>/dev/null; then
    check_ok "HA config_check (live)"
  else
    check_fail "HA config_check (live)" "$resp"
  fi
else
  echo "[SKIP] HA config_check (HA_URL/HA_TOKEN saknas — använd MCP ha_get_system_health efter deploy)"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "=== $PASS/$TOTAL kontroller OK ==="
  echo "Fortsätt med deploy + beteendetest enligt docs/verifiering-och-test.md"
  exit 0
fi

echo "=== $PASS/$TOTAL kontroller OK, minst ett fel ===" >&2
exit 1
