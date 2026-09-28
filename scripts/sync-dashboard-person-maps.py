#!/usr/bin/env python3
"""Synka personmarkörer (entity + initialer) på Spion-kartor i Översikt-dashboarden.

Kör efter export från HA eller när map-kort ändrats manuellt:
  python3 scripts/sync-dashboard-person-maps.py --patch

Källa: scripts/lib/person_map_display.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILE = ROOT / "dashboards" / "dashboard-september-2025.yaml"

sys.path.insert(0, str(ROOT / "scripts"))
from lib.person_map_display import (  # noqa: E402
    MAP_PERSON_BEGIN,
    MAP_PERSON_END,
    PERSON_MAP_DISPLAYS,
)


def build_person_block(slug: str, entity: str, initials: str) -> str:
    return (
        f"      {MAP_PERSON_BEGIN} {slug}\n"
        f"      - entity: {entity}\n"
        f"        label: {initials}\n"
        f"      {MAP_PERSON_END}"
    )


def normalize_person_comment_indent(content: str) -> str:
    """Rätta felindenterade map-person-kommentarer efter manuella dashboard-redigeringar."""
    return re.sub(
        rf"^[ \t]+({re.escape(MAP_PERSON_BEGIN)} .+)$",
        r"      \1",
        content,
        flags=re.MULTILINE,
    )


def patch_person_blocks(content: str) -> tuple[str, int]:
    updated = content
    changes = 0
    for person in PERSON_MAP_DISPLAYS:
        block = build_person_block(person.slug, person.entity_for_map, person.initials)
        pattern = re.compile(
            re.escape(MAP_PERSON_BEGIN)
            + rf" {re.escape(person.slug)}\n.*?"
            + re.escape(MAP_PERSON_END),
            re.DOTALL,
        )
        if not pattern.search(updated):
            raise SystemExit(
                f"Saknar {MAP_PERSON_BEGIN} {person.slug} i {DASHBOARD_FILE}. "
                "Lägg till markörblocket på rätt map-kort."
            )
        new_content = pattern.sub(block, updated, count=1)
        if new_content != updated:
            changes += 1
        updated = new_content

        title_pattern = re.compile(
            rf"(^\s+- type: map\n\s+title: ){re.escape(person.title)}(\n\s+entities:)",
            re.MULTILINE,
        )
        if not title_pattern.search(updated):
            raise SystemExit(
                f"Saknar map-kort med title {person.title!r} för {person.slug}"
            )
    return updated, changes


def patch_dashboard() -> None:
    content = DASHBOARD_FILE.read_text(encoding="utf-8")
    updated, changes = patch_person_blocks(content)
    if updated == content:
        print("Person-map: inga ändringar behövdes", file=sys.stderr)
        return
    DASHBOARD_FILE.write_text(updated, encoding="utf-8")
    print(f"Person-map: uppdaterade {changes} block", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patch",
        action="store_true",
        help="Skriv personmarkörer till dashboard YAML",
    )
    args = parser.parse_args()
    if args.patch:
        patch_dashboard()
        return
    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
