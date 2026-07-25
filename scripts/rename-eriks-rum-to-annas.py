#!/usr/bin/env python3
"""Byt rumsrelaterade eriks-referenser till annas i YAML-filer."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FILES = [
    "templates.yaml",
    "scripts.yaml",
    "input_text.yaml",
    "input_select.yaml",
    "input_number.yaml",
    "input_datetime.yaml",
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
    ("settings_rullgardiner_eriks_rum_elevation_ner", "settings_rullgardiner_annas_rum_elevation_ner"),
    ("settings_rullgardiner_eriks_rum_azimuth_upp", "settings_rullgardiner_annas_rum_azimuth_upp"),
    ("automation_eriks_rum_rullgardin_automatic_logic_v3", "automation_annas_rum_rullgardin_automatic_logic_v3"),
    ("eriks_rum_skrivbord_rorelse_battery", "annas_rum_skrivbord_rorelse_battery"),
    ("eriks_rum_rorelse_battery_2", "annas_rum_rorelse_battery_2"),
    ("eriks_rum_temperatur_battery", "annas_rum_temperatur_battery"),
    ("fjarr_rullgardin_eriks_rum_batteri", "fjarr_rullgardin_annas_rum_batteri"),
    ("luftkvalitet_eriks_rum_pm25", "luftkvalitet_annas_rum_pm25"),
    ("luftkvalitet_eriks_rum_ppb", "luftkvalitet_annas_rum_ppb"),
    ("rullgardin_eriks_rum_batteri", "rullgardin_annas_rum_batteri"),
    ("googlehome_eriks_rum_las_upp", "googlehome_annas_rum_las_upp"),
    ("stall_in_ljuset_i_eriks_myshorna", "stall_in_ljuset_i_annas_myshorna"),
    ("eriks_rum_stall_in_belysningen", "annas_rum_stall_in_belysningen"),
    ("eriks_myshorna_nattljusstyrka", "annas_myshorna_nattljusstyrka"),
    ("eriks_myshorna_nattljus_tid", "annas_myshorna_nattljus_tid"),
    ("lampa_eriks_jordglob_switch", "lampa_annas_jordglob_switch"),
    ("lampa_eriks_fonster_switch", "lampa_annas_fonster_switch"),
    ("lampan_i_eriks_fonster", "lampan_i_annas_fonster"),
    ("taklampan_eriks_rum_level", "taklampan_annas_rum_level"),
    ("fjarr_rullgardin_eriks_rum", "fjarr_rullgardin_annas_rum"),
    ("eriks_rum_luftfuktighet", "annas_rum_luftfuktighet"),
    ("eriks_rum_ljusstyrka", "annas_rum_ljusstyrka"),
    ("eriks_skrivbord_rorelse", "annas_skrivbord_rorelse"),
    ("eriks_rum_lufttryck", "annas_rum_lufttryck"),
    ("eriks_rum_belysning", "annas_rum_belysning"),
    ("eriks_rum_rorelse", "annas_rum_rorelse"),
    ("googlehome_eriks_rum", "googlehome_annas_rum"),
    ("rullgardin_eriks_rum", "rullgardin_annas_rum"),
    ("led_under_eriks_byra", "led_under_annas_byra"),
    ("eriks_fonster_battery", "annas_fonster_battery"),
    ("fjarr_eriks_rum", "fjarr_annas_rum"),
    ("eriks_myshorna", "annas_myshorna"),
    ("eriks_jordglob", "annas_jordglob"),
    ("eriks_fonster", "annas_fonster"),
    ("eriks_stereo", "annas_stereo"),
    ("eriks_rum_temp", "annas_rum_temp"),
    ("eriks_rum", "annas_rum"),
]

DISPLAY_REPLACEMENTS = [
    ("Rullgardinen i Eriks rum", "Rullgardinen i Annas rum"),
    ("Ställ in belysningen i Eriks rum", "Ställ in belysningen i Annas rum"),
    ("Ställ in ljuset i Eriks myshörna", "Ställ in ljuset i Annas myshörna"),
    ("Belysning: Eriks myshörna återställ efter unavailable", "Belysning: Annas myshörna återställ efter unavailable"),
    ("Belysning: Styr och verkställ belysningen i Eriks rum", "Belysning: Styr och verkställ belysningen i Annas rum"),
    ("Rullgardiner: Styr rullgardinen i Eriks rum", "Rullgardiner: Styr rullgardinen i Annas rum"),
    ("Eriks myshörna nattljusstyrka", "Annas myshörna nattljusstyrka"),
    ("Eriks myshörna nattljus from kl", "Annas myshörna nattljus from kl"),
    ("Pucken i Eriks rum", "Pucken i Annas rum"),
    ("Belysning i Eriks rum", "Belysning i Annas rum"),
    ("GH Eriks rum", "GH Annas rum"),
    ("Eriks myshörna", "Annas myshörna"),
    ("Eriks myshöna", "Annas myshörna"),
    ("Eriks skrivbord", "Annas skrivbord"),
    ("Eriks fönster", "Annas fönster"),
    ("Eriks stereo", "Annas stereo"),
    ("i Eriks rum", "i Annas rum"),
    ("Eriks rum", "Annas rum"),
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
