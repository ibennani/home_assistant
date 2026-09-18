#!/usr/bin/env python3
"""Patch house_time_modes Jinja in automations.yaml for Erik/Isabelle barn-logik."""
from __future__ import annotations

from pathlib import Path

AUTOMATIONS = Path(__file__).resolve().parents[1] / "automations.yaml"

TRIGGER_OLD = """  - trigger: state
    entity_id:
    - sensor.ilias_s23_ultra_charger_type
    - sensor.anna_s22_ultra_charger_type
    not_from:"""

TRIGGER_NEW = """  - trigger: state
    entity_id:
    - sensor.erik_aktiv_zon
    - sensor.isabelle_aktiv_zon
    to: zone.home
    not_from:
    - unavailable
    - unknown
  - trigger: state
    entity_id:
    - sensor.erik_aktiv_zon
    - sensor.isabelle_aktiv_zon
    from: zone.home
    for: 00:02:00
    not_to:
    - unavailable
    - unknown
  - trigger: state
    entity_id:
    - sensor.ilias_s23_ultra_charger_type
    - sensor.anna_s22_ultra_charger_type
    - sensor.erik_s23_charger_type
    not_from:"""

VAR_OLD = (
    "{% set ilias_hemma = is_state('binary_sensor.ilias_hemma',"
    "\\ 'on') %} {% set anna_hemma  = is_state('binary_sensor.anna_hemma', 'on') %} {% set någon_hemma = ilias_hemma or"
    "\\ anna_hemma %}\\n{% set ilias_mobil_laddar = is_state('sensor.ilias_s23_ultra_charger_type','ac') %} {% set annas_mobil_laddar"
)

VAR_NEW = (
    "{% set ilias_hemma = is_state('binary_sensor.ilias_hemma',"
    "\\ 'on') %} {% set anna_hemma  = is_state('binary_sensor.anna_hemma', 'on') %}"
    " {% set vuxen_hemma = ilias_hemma or anna_hemma %}"
    " {% set erik_hemma = is_state('binary_sensor.erik_hemma', 'on') %}"
    " {% set isabelle_hemma = is_state('binary_sensor.isabelle_hemma', 'on') %}"
    " {% set barn_hemma = erik_hemma or isabelle_hemma %}"
    " {% set huset_tomt = not vuxen_hemma and not barn_hemma %}"
    " {% set någon_hemma = vuxen_hemma %}"
    "\\n{% set ilias_mobil_laddar = is_state('sensor.ilias_s23_ultra_charger_type','ac') %} {% set annas_mobil_laddar"
    "\\ = is_state('sensor.anna_s22_ultra_charger_type','ac') %}"
    " {% set erik_mobil_laddar = is_state('sensor.erik_s23_charger_type','ac') %}"
    "\\n{% set ilias_mobil_laddar_dup = ilias_mobil_laddar %}"
)

# Remove accidental dup - fix VAR_NEW properly
VAR_NEW = (
    "{% set ilias_hemma = is_state('binary_sensor.ilias_hemma',"
    "\\ 'on') %} {% set anna_hemma  = is_state('binary_sensor.anna_hemma', 'on') %}"
    " {% set vuxen_hemma = ilias_hemma or anna_hemma %}"
    " {% set erik_hemma = is_state('binary_sensor.erik_hemma', 'on') %}"
    " {% set isabelle_hemma = is_state('binary_sensor.isabelle_hemma', 'on') %}"
    " {% set barn_hemma = erik_hemma or isabelle_hemma %}"
    " {% set huset_tomt = not vuxen_hemma and not barn_hemma %}"
    " {% set någon_hemma = vuxen_hemma %}"
    "\\n{% set ilias_mobil_laddar = is_state('sensor.ilias_s23_ultra_charger_type','ac') %} {% set annas_mobil_laddar"
    "\\ = is_state('sensor.anna_s22_ultra_charger_type','ac') %}"
    " {% set erik_mobil_laddar = is_state('sensor.erik_s23_charger_type','ac') %}"
)

KEEP_OLD = (
    "  {# Tvinga kvar Kväll fram till cutoff eller tills laddvillkor uppfylls #}\\n"
    "  {% set keep_evening =\\n   \\"
    "        \\ current_mode == 'Kväll'\\n"
    "    and någon_hemma\\n"
    "    and now_ts < cutoff_ts\\n"
    "    and not (now_ts >= laddtid_ts and\\"
    "\\ laddvillkor_ok)\\n"
    "  %}"
)

KEEP_NEW = (
    "  {# Tvinga kvar Kväll: vuxna (laddning) eller barn utan vuxen (Erik laddar / Isabelle till cutoff) #}\\n"
    "  {% set keep_evening =\\n"
    "    (current_mode == 'Kväll'\\n"
    "     and vuxen_hemma\\n"
    "     and now_ts < cutoff_ts\\n"
    "     and not (now_ts >= laddtid_ts and laddvillkor_ok))\\n"
    "    or (current_mode == 'Kväll'\\n"
    "     and not vuxen_hemma\\n"
    "     and erik_hemma\\n"
    "     and now_ts < cutoff_ts\\n"
    "     and not (now_ts >= laddtid_ts and erik_mobil_laddar))\\n"
    "    or (current_mode == 'Kväll'\\n"
    "     and not vuxen_hemma\\n"
    "     and isabelle_hemma\\n"
    "     and not erik_hemma\\n"
    "     and now_ts < cutoff_ts)\\n"
    "  %}"
)

KVALL_NATT_INSERT_BEFORE = (
    "    {# Ingen hemma #}\\n"
    "    {% elif not någon_hemma and veckodag in [7,1,2,3,4]"
)

KVALL_NATT_INSERT = (
    "    {% elif current_mode == 'Kväll' and not vuxen_hemma and erik_hemma and now_ts >= laddtid_ts and erik_mobil_laddar %}\\n"
    "      {% set ns.mode = 'Natt' %}\\n"
    "    {% elif current_mode == 'Kväll' and not vuxen_hemma and erik_hemma and now_ts >= cutoff_ts %}\\n"
    "      {% set ns.mode = 'Natt' %}\\n"
    "    {% elif current_mode == 'Kväll' and not vuxen_hemma and isabelle_hemma and not erik_hemma and now_ts >= cutoff_ts %}\\n"
    "      {% set ns.mode = 'Natt' %}\\n"
    "\\n"
    "    {# Ingen hemma (vuxen eller barn) #}\\n"
    "    {% elif huset_tomt and veckodag in [7,1,2,3,4]"
)

VACATION_KEEP_OLD = (
    "  {% set keep_evening =\\n"
    "    current_mode == 'Kväll'\\n"
    "    and någon_hemma\\n"
    "    and now_ts < cutoff_ts\\n"
    "    and not (now_ts >= laddtid_ts and laddvillkor_ok)\\n"
    "  %}"
)

VACATION_KEEP_NEW = KEEP_NEW.replace(
    "  {# Tvinga kvar Kväll: vuxna (laddning) eller barn utan vuxen (Erik laddar / Isabelle till cutoff) #}\\n",
    "  {# Tvinga kvar Kväll (semester): samma som vardag #}\\n",
)


def main() -> None:
    text = AUTOMATIONS.read_text(encoding="utf-8")
    if "huset_tomt" in text:
        print("Already patched")
        return

    if TRIGGER_OLD not in text:
        raise SystemExit("TRIGGER_OLD not found")
    text = text.replace(TRIGGER_OLD, TRIGGER_NEW, 1)

    if VAR_OLD not in text:
        raise SystemExit("VAR_OLD not found")
    text = text.replace(VAR_OLD, VAR_NEW, 1)

    if KEEP_OLD not in text:
        raise SystemExit("KEEP_OLD not found")
    text = text.replace(KEEP_OLD, KEEP_NEW, 1)

    # Natt före morgontid: not någon_hemma -> huset_tomt (only in house_time_modes block)
    start = text.find("alias: 'Huset: Styr huslägen (house_time_modes)")
    end = text.find("alias: 'Husläge: Till morgon'", start)
    block = text[start:end]
    block_new = block.replace("(not någon_hemma or", "(huset_tomt or")
    if block == block_new:
        raise SystemExit("Expected not någon_hemma patterns in block")
    text = text[:start] + block_new + text[end:]

    if KVALL_NATT_INSERT_BEFORE not in text:
        raise SystemExit("KVALL_NATT_INSERT_BEFORE not found")
    text = text.replace(KVALL_NATT_INSERT_BEFORE, KVALL_NATT_INSERT, 1)

    # Second ingen hemma branch (fre/lor)
    text = text.replace(
        "    {% elif not någon_hemma and\\n          veckodag in [5,6]",
        "    {% elif huset_tomt and\\n          veckodag in [5,6]",
        1,
    )

    if VACATION_KEEP_OLD not in text:
        raise SystemExit("VACATION_KEEP_OLD not found")
    text = text.replace(VACATION_KEEP_OLD, VACATION_KEEP_NEW, 1)

    text = text.replace(
        "    {# Ingen hemma -> Natt (lediga) #}\\n"
        "    {% elif not någon_hemma and nattid_lediga_ts",
        "    {# Ingen hemma -> Natt (lediga) #}\\n"
        "    {% elif huset_tomt and nattid_lediga_ts",
        1,
    )

    AUTOMATIONS.write_text(text, encoding="utf-8")
    print("Patched automations.yaml")


if __name__ == "__main__":
    main()
