#!/usr/bin/env python3
"""Byt aktiv_zon is_state/not is_state till binary_sensor hemma/borta_kand."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "automations.yaml",
    ROOT / "scripts.yaml",
    ROOT / "includes" / "template.yaml",
]

SLUGS = ["anna", "erik", "isabelle", "ilias"]


def migrate(content: str) -> tuple[str, int]:
    changes = 0
    for slug in SLUGS:
        patterns = [
            (
                rf"not\s+is_state\(\s*\\?\"sensor\.{slug}_aktiv_zon\\?\"\s*,\s*\\?\"zone\.home\\?\"\s*\)",
                f"is_state('binary_sensor.{slug}_borta_kand', 'on')",
            ),
            (
                rf"not\s+is_state\(\s*['\"]sensor\.{slug}_aktiv_zon['\"]\s*,\s*['\"]zone\.home['\"]\s*\)",
                f"is_state('binary_sensor.{slug}_borta_kand', 'on')",
            ),
            (
                rf"not\s+is_state\(\s*['']sensor\.{slug}_aktiv_zon['']\s*,\s*['']zone\.home['']\s*\)",
                f"is_state(''binary_sensor.{slug}_borta_kand'', ''on'')",
            ),
            (
                rf"is_state\(\s*\\?\"sensor\.{slug}_aktiv_zon\\?\"\s*,\s*\\?\"zone\.home\\?\"\s*\)",
                f"is_state('binary_sensor.{slug}_hemma', 'on')",
            ),
            (
                rf"is_state\(\s*['\"]sensor\.{slug}_aktiv_zon['\"]\s*,\s*['\"]zone\.home['\"]\s*\)",
                f"is_state('binary_sensor.{slug}_hemma', 'on')",
            ),
            (
                rf"is_state\(\s*['']sensor\.{slug}_aktiv_zon['']\s*,\s*['']zone\.home['']\s*\)",
                f"is_state(''binary_sensor.{slug}_hemma'', ''on'')",
            ),
        ]
        for pattern, repl in patterns:
            new_content, n = re.subn(pattern, repl, content)
            content = new_content
            changes += n
    return content, changes


def main() -> None:
    total = 0
    for path in FILES:
        if not path.exists():
            print(f"Skip {path} (missing)", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        migrated, n = migrate(original)
        if n:
            path.write_text(migrated, encoding="utf-8")
            print(f"{path}: {n} replacements", file=sys.stderr)
            total += n
        else:
            print(f"{path}: no changes", file=sys.stderr)
    print(f"Total: {total} replacements", file=sys.stderr)
    if total == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
