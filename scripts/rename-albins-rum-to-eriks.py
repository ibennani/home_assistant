#!/usr/bin/env python3
"""Byt rumsrelaterade albins-referenser till eriks i YAML-filer."""
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
    ("lights_taklamporna_i_albins_rum", "lights_taklamporna_i_eriks_rum"),
    ("automation_albins_rum_rullgardin_oppna_vid_fritt_fram", "automation_eriks_rum_rullgardin_oppna_vid_fritt_fram"),
    ("albins_rum_temperatur_battery_2", "eriks_rum_temperatur_battery_2"),
    ("oversvamning_albins_fonster", "oversvamning_eriks_fonster"),
    ("hyllan_ovanfor_albins_sang", "hyllan_ovanfor_eriks_sang"),
    ("luftkvalitet_ppb_albins_rum", "luftkvalitet_ppb_eriks_rum"),
    ("luftkvalitet_albins_rum_pm25", "luftkvalitet_eriks_rum_pm25"),
    ("fjarr_2_albins_rum_battery", "fjarr_2_eriks_rum_battery"),
    ("rullgardin_albins_rum_batteri", "rullgardin_eriks_rum_batteri"),
    ("googlehome_albins_rum_las_upp", "googlehome_eriks_rum_las_upp"),
    ("albins_rum_stall_in_belysningen", "eriks_rum_stall_in_belysningen"),
    ("taklampan_albins_fonster_level", "taklampan_eriks_fonster_level"),
    ("taklampan_albins_sang_level", "taklampan_eriks_sang_level"),
    ("albins_lavalampa_switch", "eriks_lavalampa_switch"),
    ("albins_rum_luftfuktighet", "eriks_rum_luftfuktighet"),
    ("albins_skrivbord_rorelse", "eriks_skrivbord_rorelse"),
    ("albins_rum_rorelse_battery", "eriks_rum_rorelse_battery"),
    ("albins_rum_ljusstyrka", "eriks_rum_ljusstyrka"),
    ("albins_rum_lufttryck", "eriks_rum_lufttryck"),
    ("albins_rum_belysning", "eriks_rum_belysning"),
    ("albins_rum_rorelse", "eriks_rum_rorelse"),
    ("googlehome_albins_rum", "googlehome_eriks_rum"),
    ("rullgardin_albins_rum", "rullgardin_eriks_rum"),
    ("fjarr_2_albins_rum", "fjarr_2_eriks_rum"),
    ("albins_fonster_battery", "eriks_fonster_battery"),
    ("fjarr_albins_rum_battery", "fjarr_eriks_rum_battery"),
    ("fjarr_albins_rum", "fjarr_eriks_rum"),
    ("albins_biosalong", "eriks_biosalong"),
    ("albins_myslampa", "eriks_myslampa"),
    ("albins_garderob", "eriks_garderob"),
    ("albins_fonster", "eriks_fonster"),
    ("albins_stereo", "eriks_stereo"),
    ("albins_flakt", "eriks_flakt"),
    ("albins_rum_temp", "eriks_rum_temp"),
    ("albins_rum", "eriks_rum"),
    ("albins_tv", "eriks_tv"),
]

DISPLAY_REPLACEMENTS = [
    ("Belysning: Blinka mysbelysningen i Albins rum när det ringer på dörren", "Belysning: Blinka mysbelysningen i Eriks rum när det ringer på dörren"),
    ("Belysning: Styr belysningen och rullgardinen i Albins rum", "Belysning: Styr belysningen och rullgardinen i Eriks rum"),
    ("Belysning: Kör script som styr belysningen i Albins rum", "Belysning: Kör script som styr belysningen i Eriks rum"),
    ("Belysning: Styr belysningen i garderoben i Albins rum", "Belysning: Styr belysningen i garderoben i Eriks rum"),
    ("Media: Ställ in volymen på pucken i Albins rum när Storytel spelar på kvällarna", "Media: Ställ in volymen på pucken i Eriks rum när Storytel spelar på kvällarna"),
    ("Media: Stäng av pucken i Albins rum efter x minuter när Storytel spelar", "Media: Stäng av pucken i Eriks rum efter x minuter när Storytel spelar"),
    ("Ställ in belysningen i Albins rum", "Ställ in belysningen i Eriks rum"),
    ("Taklamporna i Albins rum", "Taklamporna i Eriks rum"),
    ("Taklampan ovanför Albins fönster", "Taklampan ovanför Eriks fönster"),
    ("Taklampan ovanför Albins säng", "Taklampan ovanför Eriks säng"),
    ("Pucken i Albins rum", "Pucken i Eriks rum"),
    ("Belysning i Albins rum", "Belysning i Eriks rum"),
    ("GH Albins rum", "GH Eriks rum"),
    ("Albins garderob", "Eriks garderob"),
    ("Albins skrivbord", "Eriks skrivbord"),
    ("Albins fönster", "Eriks fönster"),
    ("Albins stereo", "Eriks stereo"),
    ("Albins myslampa", "Eriks myslampa"),
    ("i Albins rum", "i Eriks rum"),
    ("Albins rum", "Eriks rum"),
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
