#!/usr/bin/env python3
"""Kontrollera att kartor använder rätt initialer, entitet och förnamn (tooltip)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboards" / "dashboard-september-2025.yaml"
TEMPLATE = ROOT / "includes" / "template.yaml"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.person_map_display import (  # noqa: E402
    MAP_PERSON_BEGIN,
    MAP_PERSON_END,
    PERSON_MAP_DISPLAYS,
)

SPION_BEGIN = "# BEGIN spion-karta-sensorer (generate-ilias-zone-automation.py)"
SPION_END = "# END spion-karta-sensorer (generate-ilias-zone-automation.py)"


def extract_block(text: str, begin: str, end: str) -> str:
    pattern = re.compile(re.escape(begin) + r"(.*?)" + re.escape(end), re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Saknar block {begin!r} … {end!r}")
    return match.group(1)


def check_dashboard(content: str, errors: list[str]) -> None:
    for person in PERSON_MAP_DISPLAYS:
        pattern = re.compile(
            re.escape(MAP_PERSON_BEGIN)
            + rf" {re.escape(person.slug)}\n(.*?)\n\s+{re.escape(MAP_PERSON_END)}",
            re.DOTALL,
        )
        match = pattern.search(content)
        if not match:
            errors.append(f"dashboard: saknar map-person-block för {person.slug}")
            continue
        block = match.group(1)
        if person.entity_for_map not in block:
            errors.append(
                f"dashboard: {person.slug} ska använda {person.entity_for_map}, inte annan entitet"
            )
        label_match = re.search(r"label:\s*(\S+)", block)
        if not label_match or label_match.group(1) != person.initials:
            errors.append(
                f"dashboard: {person.slug} ska ha label {person.initials!r}, "
                f"fick {label_match.group(1) if label_match else 'inget'!r}"
            )


def check_spion_sensors(template_block: str, errors: list[str]) -> None:
    for person in PERSON_MAP_DISPLAYS:
        if not person.spion_template:
            continue
        slug_pat = rf"unique_id:\s*{re.escape(person.slug)}_spionkarta"
        if not re.search(slug_pat, template_block):
            errors.append(f"template: saknar sensor {person.spion_entity}")
            continue
        # name direkt efter unique_id-raden för den sensorn
        chunk = re.search(
            rf"unique_id:\s*{re.escape(person.slug)}_spionkarta\n\s+- name:\s*(.+)\n",
            template_block,
        )
        if not chunk:
            # HA YAML: name före unique_id
            chunk = re.search(
                rf"- name:\s*(.+)\n\s+unique_id:\s*{re.escape(person.slug)}_spionkarta",
                template_block,
            )
        if not chunk:
            errors.append(f"template: kunde inte läsa name för {person.slug}_spionkarta")
            continue
        name = chunk.group(1).strip()
        if name != person.first_name:
            errors.append(
                f"template: {person.slug}_spionkarta ska heta {person.first_name!r} "
                f"(tooltip), heter {name!r}"
            )


def main() -> int:
    errors: list[str] = []
    dash = DASHBOARD.read_text(encoding="utf-8")
    check_dashboard(dash, errors)

    template = TEMPLATE.read_text(encoding="utf-8")
    spion_block = extract_block(template, SPION_BEGIN, SPION_END)
    check_spion_sensors(spion_block, errors)

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        print(
            "Tips: python3 scripts/generate-ilias-zone-automation.py --patch-templates "
            "&& python3 scripts/sync-dashboard-person-maps.py --patch",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(PERSON_MAP_DISPLAYS)} personkartor enligt person_map_display.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
