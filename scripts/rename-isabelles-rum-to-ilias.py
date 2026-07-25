#!/usr/bin/env python3
"""Byt rumsrelaterade isabelles-referenser till ilias i YAML-filer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    "templates.yaml",
    "scripts.yaml",
    "input_text.yaml",
    "input_select.yaml",
    "includes/var.yaml",
    "includes/template.yaml",
    "includes/skalskydd_sensors.yaml",
    "includes/sensor.yaml",
    "includes/notify.yaml",
    "includes/media_player.yaml",
    "groups.yaml",
    "automations.yaml",
    "archive/ui-lovelace.yaml",
]

# Längre mönster först
SLUG_REPLACEMENTS = [
    ("lamporna_ovanfor_isabelles_sang", "lamporna_ovanfor_ilias_sang"),
    ("lamporna_i_isabelles_fonster", "lamporna_i_ilias_fonster"),
    ("fjarr_rullgardin_isabelles_rum", "fjarr_rullgardin_ilias_rum"),
    ("fjarr_taklampan_i_isabelles_rum", "fjarr_taklampan_i_ilias_rum"),
    ("brandvarnaren_i_isabelles_rum", "brandvarnaren_i_ilias_rum"),
    ("taklampan_isabelles_rum", "taklampan_ilias_rum"),
    ("taklampan_i_isabelles_rum", "taklampan_i_ilias_rum"),
    ("googlehome_isabelles_rum", "googlehome_ilias_rum"),
    ("pucken_i_isabelles_rum", "pucken_i_ilias_rum"),
    ("rullgardin_isabelles_rum", "rullgardin_ilias_rum"),
    ("test_spela_p1_i_isabelles_rum", "test_spela_p1_i_ilias_rum"),
    ("styr_rullgardin_isabelles_rum", "styr_rullgardin_ilias_rum"),
    ("isabelles_rum_stall_in_belysningen", "ilias_rum_stall_in_belysningen"),
    ("isabelles_rum_styr_belysningen", "ilias_rum_styr_belysningen"),
    ("input_boolean_isabelles_rum", "input_boolean_ilias_rum"),
    ("ac_ska_slacka_isabelles_rum", "ac_ska_slacka_ilias_rum"),
    ("isabelle_belysning_lage", "ilias_belysning_lage"),
    ("belysning_isabelles_rum", "belysning_ilias_rum"),
    ("isabelles_skrivbord", "ilias_skrivbord"),
    ("isabelles_myslampa", "ilias_myslampa"),
    ("isabelles_fonster", "ilias_fonster"),
    ("fjarr_isabelles_rum", "fjarr_ilias_rum"),
    ("isabelles_mode", "ilias_mode"),
    ("isabeles_taklampa", "ilias_taklampa"),
    ("isabelles_rum", "ilias_rum"),
]

DISPLAY_REPLACEMENTS = [
    ("Pucken i Isabelles rum", "Pucken i Ilias rum"),
    ("Belysning i Isabelles rum", "Belysning i Ilias rum"),
    ("GH Isabelles rum", "GH Ilias rum"),
    ("Dimma Isabelles taklampa", "Dimma Ilias taklampa"),
    ("Google home mini i Isabelles rum", "Google home mini i Ilias rum"),
    ("Lamporna ovanför Isabelles säng", "Lamporna ovanför Ilias säng"),
    ("Lamporna i Isabelles fönster", "Lamporna i Ilias fönster"),
    ("Isabelles myslampa", "Ilias myslampa"),
    ("Isabelles skrivbord", "Ilias skrivbord"),
    ("Isabelles fönster", "Ilias fönster"),
    ("Isabelles taklampa", "Ilias taklampa"),
    ("i Isabelles rum", "i Ilias rum"),
    ("Isabelles rum", "Ilias rum"),
]


def transform(content: str) -> str:
    for old, new in SLUG_REPLACEMENTS:
        content = content.replace(old, new)
    for old, new in DISPLAY_REPLACEMENTS:
        content = content.replace(old, new)
    return content


def main() -> None:
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            print(f"SKIP (saknas): {rel}")
            continue
        original = path.read_text(encoding="utf-8")
        updated = transform(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            print(f"UPDATED: {rel}")
        else:
            print(f"UNCHANGED: {rel}")


if __name__ == "__main__":
    main()
