#!/usr/bin/env python3
"""Säkerställ att kostnads-YAML inte refererar rå Nord Pool."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOT = "sensor.nordpool_kwh_se3_sek_3_10_025"

# Filer där spot är tillåten (definition av marginal-sensor, dashboard börs-rad)
ALLOWED = {
    ROOT / "includes" / "template.yaml",
    ROOT / "dashboards" / "dashboard-september-2025.yaml",
}

SCAN = [
    ROOT / "automations.yaml",
    ROOT / "scripts.yaml",
    ROOT / "templates.yaml",
    ROOT / "includes" / "template.yaml",
]

PY_SCAN = list((ROOT / "scripts").glob("*.py"))

# Python med spot endast som reserv (primär källa: marginal-sensor)
PY_ALLOWED = {
    "tvattmaskin-berakna-kostnad-klar.py",
}


def _strip_script_block(text: str, marker: str, next_markers: list[str]) -> str:
    start = text.find(marker)
    if start < 0:
        return text
    end = len(text)
    for nm in next_markers:
        pos = text.find(nm, start + len(marker))
        if pos >= 0:
            end = min(end, pos)
    return text[:start] + text[end:]


def _strip_exempt_blocks(text: str, path: Path) -> str:
    """Prognos och minut-tick läser spot + samma öre-tillägg som marginal-sensorn."""
    if path.name != "scripts.yaml":
        return text
    text = _strip_script_block(
        text,
        "diskmaskin_prognos_kostnad:",
        ["\n\ndiskmaskin_", "\n\ntvattmaskin_", "\n\nvitvaror_"],
    )
    text = _strip_script_block(
        text,
        "vitvaror_el_kostnad_minut_tick:",
        ["\n\ndiskmaskin_", "\n\ntvattmaskin_"],
    )
    return text


def check_file(path: Path) -> list[str]:
    if path in ALLOWED:
        return []
    text = _strip_exempt_blocks(path.read_text(encoding="utf-8"), path)
    if SPOT not in text:
        return []
    hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        if SPOT in line:
            hits.append(f"{path.relative_to(ROOT)}:{i}")
    return hits


def main() -> int:
    errors: list[str] = []
    for path in SCAN:
        if path.is_file():
            errors.extend(check_file(path))
    for path in PY_SCAN:
        if path.name == "check-elpris-source.py":
            continue
        text = path.read_text(encoding="utf-8")
        if SPOT in text:
            errors.append(f"{path.relative_to(ROOT)} (Python refererar spot)")

    if errors:
        print("Kostnadsfiler får inte använda Nord Pool spot direkt:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"Använd sensor.elpris_marginal_kwh_se3 — se docs/elpris-marginal.md", file=sys.stderr)
        return 1
    print("check-elpris-source: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
