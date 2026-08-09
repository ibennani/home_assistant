#!/usr/bin/env python3
"""Generera aktiv_zon-sensorer och platsnotis-automation (mittpunkt i zon)."""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = ROOT / "includes" / "template.yaml"
AUTOMATIONS_FILE = ROOT / "automations.yaml"

# tracker_entity, visningsnamn, sensor-slug (sensor.<slug>_aktiv_zon)
AKTIV_ZON_PEOPLE = [
    ("person.anna_bennani", "Anna", "anna"),
    ("person.erik_bennani", "Erik", "erik"),
    ("person.isabelle_sovig", "Isabelle", "isabelle"),
    ("person.ilias_bennani", "Ilias", "ilias"),
]

# Ilias platsnotiser: övriga familjemedlemmar (ej Ilias själv)
TRACKED_PEOPLE = [p for p in AKTIV_ZON_PEOPLE if p[2] != "ilias"]

# Annas hemma-notiser: övriga familjemedlemmar (ej Anna själv)
ANNA_TRACKED_PEOPLE = [p for p in AKTIV_ZON_PEOPLE if p[2] != "anna"]

ZONES = [
    ("zone.home", "home"),
    ("zone.annas_jobb", "annas_jobb"),
    ("zone.eriks_skola", "eriks_skola"),
    ("zone.ilias_jobb", "ilias_jobb"),
    ("zone.srf_stockholm", "srf_stockholm"),
    ("zone.kth_campus", "kth_campus"),
    ("zone.kth_flemmingsberg", "kth_flemmingsberg"),
    ("zone.albins_mamma", "albins_mamma"),
    ("zone.isabelles_jobb", "isabelles_jobb"),
    ("zone.albin", "albin"),
    ("zone.grasko", "grasko"),
    ("zone.isabelles_mormor", "isabelles_mormor"),
    ("zone.isabelles_skola", "isabelles_skola"),
    ("zone.goteborg_c", "goteborg_c"),
    ("zone.isabelles_moster_jenny", "isabelles_moster_jenny"),
    ("zone.adrian", "adrian"),
    ("zone.justus", "justus"),
    ("zone.rodkinda_19", "rodkinda_19"),
    ("zone.eddie", "eddie"),
    ("zone.knut", "knut"),
    ("zone.milo", "milo"),
    ("zone.hemma_hos_rio", "hemma_hos_rio"),
    ("zone.ellio_i_tanum", "ellio_i_tanum"),
    ("zone.digg_sundsvall", "digg_sundsvall"),
    ("zone.ostra_sjukhuset", "ostra_sjukhuset"),
    ("zone.stromstad", "stromstad"),
    ("zone.ik_sodra_skarpnack", "ik_sodra_skarpnack"),
    ("zone.torvallahallen", "torvallahallen"),
    ("zone.zaki_och_hanna", "zaki_och_hanna"),
    ("zone.maria", "maria"),
    ("zone.sixten", "sixten"),
    ("zone.oslo", "oslo"),
    ("zone.farmor_och_farfar", "farmor_och_farfar"),
    ("zone.solveig_och_lennart", "solveig_och_lennart"),
    ("zone.bengt", "bengt"),
    ("zone.farsta_centrum", "farsta_centrum"),
    ("zone.farsta_strand_pendeltagstation", "farsta_strand_pendeltagstation"),
    ("zone.ellio_i_norge", "ellio_i_norge"),
    ("zone.eina", "eina"),
    ("zone.gjovik", "gjovik"),
    ("zone.norge_2", "norge_2"),
    ("zone.sahlgrenska_sjukhuset", "sahlgrenska_sjukhuset"),
    ("zone.molndahls_sjukhus", "molndahls_sjukhuset"),
    ("zone.stefan", "stefan"),
    ("zone.elins_jobb", "elins_jobb"),
    ("zone.visby", "visby"),
    ("zone.gotlandslagret", "gotlandslagret"),
    ("zone.nynashamn", "nynashamn"),
    ("zone.isabelle", "isabelle"),
]

ZONE_MESSAGES = {
    "home": {
        "entered": "{{ person }} är hemma",
        "left": "{{ person }} har gått hemifrån",
    },
    "annas_jobb": {
        "entered": "{{ person }} {% if person == 'Anna' %}är på jobbet {% else %}är på Annas jobb{% endif %}",
        "left": "{{ person }} {% if person == 'Anna' %}har lämnat jobbet {% else %}har lämnat Annas jobb{% endif %}",
    },
    "eriks_skola": {
        "entered": "{{ person }} {% if person == 'Erik' %}är i skolan {% else %}är i Eriks skola{% endif %}",
        "left": "{{ person }} {% if person == 'Erik' %}har lämnat skolan {% else %}har lämnat Eriks skola{% endif %}",
    },
    "ilias_jobb": {
        "entered": "{{ person }} {% if person == 'Ilias' %}är på jobbet {% else %}är på Ilias jobb{% endif %}",
        "left": "{{ person }} {% if person == 'Ilias' %}har lämnat jobbet {% else %}har lämnat Ilias jobb{% endif %}",
    },
    "srf_stockholm": {
        "entered": "{{ person }} är på SRF Stockholm",
        "left": "{{ person }} har lämnat SRF Stockholm",
    },
    "kth_campus": {
        "entered": "{{ person }} är på KTH",
        "left": "{{ person }} har lämnat KTH",
    },
    "kth_flemmingsberg": {
        "entered": "{{ person }} är på Youssef och Emma",
        "left": "{{ person }} har lämnat Youssef och Emma",
    },
    "albins_mamma": {
        "entered": "{{ person }} är hos Albins mamma",
        "left": "{{ person }} har åkt ifrån Albins mamma",
    },
    "isabelles_jobb": {
        "entered": "{{ person }} {% if person == 'Isabelle' %}är på jobbet {% else %}är på Isabelles jobb{% endif %}",
        "left": "{{ person }} {% if person == 'Isabelle' %}har lämnat jobbet {% else %}har lämnat Isabelles jobb{% endif %}",
    },
    "albin": {
        "entered": "{{ person }} är hemma hos Albin",
        "left": "{{ person }} har åkt hemifrån Albin",
    },
    "grasko": {
        "entered": "{{ person }} är på Gräskö",
        "left": "{{ person }} har lämnat Gräskö",
    },
    "isabelles_mormor": {
        "entered": "{{ person }} {% if person == 'Isabelle' %}är hos mormor {% else %}är hos Isabelles mormor{% endif %}",
        "left": "{{ person }} {% if person == 'Isabelle' %}har åkt hemifrån mormor {% else %}har åkt ifrån Isabelles mormor{% endif %}",
    },
    "isabelles_skola": {
        "entered": "{{ person }} {% if person == 'Isabelle' %}är i skolan {% else %}är i Isabelles skola{% endif %}",
        "left": "{{ person }} {% if person == 'Isabelle' %}har lämnat skolan {% else %}har lämnat Isabelles skola{% endif %}",
    },
    "goteborg_c": {
        "entered": "{{ person }} är på Göteborg Central",
        "left": "{{ person }} har lämnat Göteborg Central",
    },
    "isabelles_moster_jenny": {
        "entered": "{{ person }} är hos moster Jenny",
        "left": "{{ person }} har lämnat moster Jenny",
    },
    "adrian": {
        "entered": "{{ person }} är hos Adrian",
        "left": "{{ person }} har lämnat Adrian",
    },
    "justus": {
        "entered": "{{ person }} är hos Justus",
        "left": "{{ person }} har lämnat Justus",
    },
    "rodkinda_19": {
        "entered": "{{ person }} är hos Rödkinda 19",
        "left": "{{ person }} har lämnat Rödkinda 19",
    },
    "eddie": {
        "entered": "{{ person }} är hos Eddie",
        "left": "{{ person }} har lämnat Eddie",
    },
    "knut": {
        "entered": "{{ person }} är hos Knut",
        "left": "{{ person }} har lämnat Knut",
    },
    "milo": {
        "entered": "{{ person }} är hos Milo",
        "left": "{{ person }} har lämnat Milo",
    },
    "hemma_hos_rio": {
        "entered": "{{ person }} är hos Rio i Norge",
        "left": "{{ person }} har lämnat Rio i Norge",
    },
    "ellio_i_tanum": {
        "entered": "{{ person }} är hos Selma i Tanum",
        "left": "{{ person }} har lämnat Selma i Tanum",
    },
    "digg_sundsvall": {
        "entered": "{{ person }} är på Stockholm centralstation",
        "left": "{{ person }} har lämnat Stockholm centralstation",
    },
    "ostra_sjukhuset": {
        "entered": "{{ person }} är på Östra sjukhuset",
        "left": "{{ person }} har lämnat Östra sjukhuset",
    },
    "stromstad": {
        "entered": "{{ person }} är i Strömstad",
        "left": "{{ person }} har lämnat Strömstad",
    },
    "ik_sodra_skarpnack": {
        "entered": "{{ person }} är i judohallen i Skarpnäck",
        "left": "{{ person }} har lämnat judohallen i Skarpnäck",
    },
    "torvallahallen": {
        "entered": "{{ person }} är i Torvallahallen",
        "left": "{{ person }} har lämnat Torvallahallen",
    },
    "zaki_och_hanna": {
        "entered": "{{ person }} är hos Zaki och Hanna",
        "left": "{{ person }} har lämnat Zaki och Hanna",
    },
    "maria": {
        "entered": "{{ person }} är hos Maria",
        "left": "{{ person }} har lämnat Maria",
    },
    "sixten": {
        "entered": "{{ person }} är hemma hos Sixten",
        "left": "{{ person }} har lämnat Sixten",
    },
    "oslo": {
        "entered": "{{ person }} är i Oslo",
        "left": "{{ person }} har lämnat Oslo",
    },
    "farmor_och_farfar": {
        "entered": "{{ person }} är hos farmor och farfar",
        "left": "{{ person }} har lämnat farmor och farfar",
    },
    "solveig_och_lennart": {
        "entered": "{{ person }} är hos Solveig och Lennart i Västerås",
        "left": "{{ person }} har lämnat Solveig och Lennart i Västerås",
    },
    "bengt": {
        "entered": "{{ person }} är hos Bengt i Nol",
        "left": "{{ person }} har lämnat Bengt i Nol",
    },
    "farsta_centrum": {
        "entered": "{{ person }} är i Farsta centrum",
        "left": "{{ person }} har lämnat Farsta centrum",
    },
    "farsta_strand_pendeltagstation": {
        "entered": "{{ person }} är på Farsta strand pendeltågstation",
        "left": "{{ person }} har lämnat Farsta strand pendeltågstation",
    },
    "ellio_i_norge": {
        "entered": "{{ person }} är hos Selma i Norge",
        "left": "{{ person }} har lämnat Selma i Norge",
    },
    "eina": {
        "entered": "{{ person }} är i Eina",
        "left": "{{ person }} har lämnat Eina",
    },
    "gjovik": {
        "entered": "{{ person }} är i Gjövik",
        "left": "{{ person }} har lämnat Gjövik",
    },
    "norge_2": {
        "entered": "{{ person }} är i Norge 2",
        "left": "{{ person }} har lämnat Norge 2",
    },
    "sahlgrenska_sjukhuset": {
        "entered": "{{ person }} är på Sahlgrenska sjukhuset",
        "left": "{{ person }} har lämnat Sahlgrenska sjukhuset",
    },
    "molndahls_sjukhus": {
        "entered": "{{ person }} är på Mölndahls sjukhus",
        "left": "{{ person }} har lämnat Mölndahls sjukhuset",
    },
    "stefan": {
        "entered": "{{ person }} är hos Stefan",
        "left": "{{ person }} har åkt ifrån Stefan",
    },
    "elins_jobb": {
        "entered": "{{ person }} är på Elins jobb",
        "left": "{{ person }} har lämnat Elins jobb",
    },
    "visby": {
        "entered": "{{ person }} är i Visby",
        "left": "{{ person }} har lämnat Visby",
    },
    "gotlandslagret": {
        "entered": "{{ person }} är på Gotlandslägret",
        "left": "{{ person }} har lämnat Gotlandslägret",
    },
    "nynashamn": {
        "entered": "{{ person }} är i Nynäshamn",
        "left": "{{ person }} har lämnat Nynäshamn",
    },
    "isabelle": {
        "entered": "{{ person }} {% if person == 'Isabelle' %}är hemma hos sig{% else %}är hos Isabelle{% endif %}",
        "left": "{{ person }} {% if person == 'Isabelle' %}har åkt hemifrån sitt hem{% else %}har lämnat Isabelle{% endif %}",
    },
}

TEMPLATE_BEGIN = "# BEGIN aktiv-zon-sensorer (generate-ilias-zone-automation.py)"
TEMPLATE_END = "# END aktiv-zon-sensorer (generate-ilias-zone-automation.py)"
AUTOMATION_ID = "7918348674111555999"
ANNA_AUTOMATION_ID = "791834010101014158674"


def all_aktiv_zon_people() -> list[tuple[str, str, str]]:
    return list(AKTIV_ZON_PEOPLE)


def zone_list_jinja(indent: str = "          ") -> str:
    lines = [f"{indent}'{zone}'," for zone, _slug in ZONES]
    if lines:
        lines[-1] = lines[-1].rstrip(",")
    return "\n".join(lines)


def aktiv_zon_state_template(tracker: str) -> str:
    return textwrap.dedent(
        f"""\
        {{% set tracker = '{tracker}' %}}
        {{% set zones = [
        {zone_list_jinja()}
        ] %}}
        {{% set ns = namespace(best='not_home', best_d=999999) %}}
        {{% if state_attr(tracker, 'latitude') is not none and state_attr(tracker, 'longitude') is not none %}}
          {{% for z in zones %}}
            {{% set d_m = distance(tracker, z) * 1000 %}}
            {{% set r = state_attr(z, 'radius') | float(0) %}}
            {{% if d_m <= r and d_m < ns.best_d %}}
              {{% set ns.best = z %}}
              {{% set ns.best_d = d_m %}}
            {{% endif %}}
          {{% endfor %}}
        {{% endif %}}
        {{{{ ns.best }}}}"""
    )


def build_template_sensors() -> str:
    lines = [TEMPLATE_BEGIN, "    # ---- Aktiv zon (mittpunkt i zon, en zon åt gången) ----"]
    for _tracker, display_name, slug in all_aktiv_zon_people():
        state_tpl = aktiv_zon_state_template(_tracker)
        lines.append(f"    - name: {display_name} aktiv zon")
        lines.append(f"      unique_id: {slug}_aktiv_zon")
        lines.append("      icon: mdi:map-marker-radius")
        lines.append("      state: >")
        for line in state_tpl.splitlines():
            lines.append(f"        {line}")
        lines.append("")
    lines.append(TEMPLATE_END)
    return "\n".join(lines)


def slug_from_state_expr(state_var: str) -> str:
    return (
        f"{{{{ {state_var}.replace('zone.', '') "
        f"if {state_var}.startswith('zone.') else {state_var} }}}}"
    )


def build_notification_message_template() -> str:
    person_lines = []
    for index, (_tracker, display_name, slug) in enumerate(TRACKED_PEOPLE):
        keyword = "if" if index == 0 else "elif"
        person_lines.append(
            f"        {{%- {keyword} trigger.entity_id == 'sensor.{slug}_aktiv_zon' -%}}\n"
            f"          {{%- set person = '{display_name}' -%}}"
        )
    person_lines.append("        {%- else -%}")
    person_lines.append("          {%- set person = 'Okänd' -%}")
    person_lines.append("        {%- endif -%}")
    person_lines.append(
        "        {%- set from_slug = trigger.from_state.state.replace('zone.', '') "
        "if trigger.from_state.state.startswith('zone.') else trigger.from_state.state -%}"
    )
    person_lines.append(
        "        {%- set to_slug = trigger.to_state.state.replace('zone.', '') "
        "if trigger.to_state.state.startswith('zone.') else trigger.to_state.state -%}"
    )

    branches: list[str] = []
    for slug, msgs in ZONE_MESSAGES.items():
        branches.append(
            f"        {{%- elif to_slug == 'not_home' and from_slug == '{slug}' -%}}\n"
            f"          {msgs['left']}"
        )
    for slug, msgs in ZONE_MESSAGES.items():
        branches.append(
            f"        {{%- elif to_slug == '{slug}' -%}}\n"
            f"          {msgs['entered']}"
        )

    body = "\n".join(person_lines) + "\n" + "\n".join(branches)
    body += (
        "\n        {%- else -%}\n"
        "          {{ person }} platsändring ({{ from_slug }} → {{ to_slug }})\n"
        "        {%- endif -%}"
    )
    body = body.replace("        {%- elif to_slug ==", "        {%- if to_slug ==", 1)
    return body


def build_automation() -> str:
    entity_ids = [f"sensor.{slug}_aktiv_zon" for _t, _n, slug in TRACKED_PEOPLE]
    message = build_notification_message_template()
    lines = [
        f"- id: '{AUTOMATION_ID}'",
        "  alias: 'Mobilnotis Ilias: Vilka kommer hem och går hemifrån'",
        "  description: Platsnotiser via aktiv_zon (mittpunkt i zon, en zon åt gången).",
        "  mode: parallel",
        "  triggers:",
        "  - trigger: state",
        "    entity_id:",
    ]
    lines.extend(f"    - {eid}" for eid in entity_ids)
    lines += [
        "  conditions:",
        "  - condition: template",
        "    value_template: >",
        "      {{ trigger.from_state.state not in ['unknown', 'unavailable', 'none']",
        "         and trigger.to_state.state not in ['unknown', 'unavailable', 'none']",
        "         and trigger.from_state.state != trigger.to_state.state }}",
        "  actions:",
        "  - variables:",
        "      notification_message: >",
    ]
    for line in message.splitlines():
        lines.append(f"        {line}")
    lines += [
        "  - action: notify.mobile_app_ilias_s23_ultra",
        "    data:",
        "      message: \"HEMMET {{ now().strftime('%R') }}: \\n{{ notification_message }}\"",
        "      data:",
        "        ttl: 0",
        "        priority: high",
        "  - action: homeassistant.update_entity",
        "    entity_id: sensor.people_home_count",
    ]
    return "\n".join(lines)


def build_anna_notification_message_template() -> str:
    person_lines = []
    for index, (_tracker, display_name, slug) in enumerate(ANNA_TRACKED_PEOPLE):
        keyword = "if" if index == 0 else "elif"
        person_lines.append(
            f"        {{%- {keyword} trigger.entity_id == 'sensor.{slug}_aktiv_zon' -%}}\n"
            f"          {{%- set person = '{display_name}' -%}}"
        )
    person_lines.append("        {%- else -%}")
    person_lines.append("          {%- set person = 'Okänd' -%}")
    person_lines.append("        {%- endif -%}")
    person_lines.append("        {%- if trigger.to_state.state == 'zone.home' -%}")
    person_lines.append("          {{ person }} är hemma")
    person_lines.append("        {%- elif trigger.from_state.state == 'zone.home' -%}")
    person_lines.append("          {{ person }} har gått hemifrån")
    person_lines.append("        {%- endif -%}")
    return "\n".join(person_lines)


def build_anna_automation() -> str:
    entity_ids = [f"sensor.{slug}_aktiv_zon" for _t, _n, slug in ANNA_TRACKED_PEOPLE]
    message = build_anna_notification_message_template()
    lines = [
        "- alias: 'Mobilnotis Anna: Vilka kommer hem och går hemifrån'",
        f"  id: '{ANNA_AUTOMATION_ID}'",
        "  description: Hemma-notiser till Anna via aktiv_zon (mittpunkt i zone.home).",
        "  mode: parallel",
        "  triggers:",
        "  - trigger: state",
        "    entity_id:",
    ]
    lines.extend(f"    - {eid}" for eid in entity_ids)
    lines += [
        "  conditions:",
        "  - condition: template",
        "    value_template: >",
        "      {{ trigger.from_state.state not in ['unknown', 'unavailable', 'none']",
        "         and trigger.to_state.state not in ['unknown', 'unavailable', 'none']",
        "         and trigger.from_state.state != trigger.to_state.state",
        "         and ('zone.home' in [trigger.from_state.state, trigger.to_state.state]) }}",
        "  actions:",
        "  - variables:",
        "      notification_message: >",
    ]
    for line in message.splitlines():
        lines.append(f"        {line}")
    lines += [
        "  - action: notify.mobile_app_anna_s22_ultra",
        "    data:",
        "      message: \"HEMMET {{ now().strftime('%R') }}: \\n{{ notification_message }}\"",
        "      data:",
        "        ttl: 0",
        "        priority: high",
    ]
    return "\n".join(lines)


def replace_marked_block(content: str, begin: str, end: str, new_block: str) -> str:
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(content):
        raise ValueError(f"Marker block not found: {begin} ... {end}")
    return pattern.sub(new_block, content, count=1)


def replace_automation(content: str, new_automation: str) -> str:
    pattern = re.compile(
        rf"- id: '{AUTOMATION_ID}'.*?(?=\n- alias: 'Mobilnotis Anna:)",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Automation {AUTOMATION_ID} not found")
    return pattern.sub(new_automation + "\n", content, count=1)


def replace_anna_automation(content: str, new_automation: str) -> str:
    pattern = re.compile(
        rf"- alias: 'Mobilnotis Anna: Vilka kommer hem och går hemifrån'\n"
        rf"  id: '{ANNA_AUTOMATION_ID}'.*?(?=\n- alias: 'Mobilnotis: Posten har kommit')",
        re.DOTALL,
    )
    if not pattern.search(content):
        raise ValueError(f"Automation {ANNA_AUTOMATION_ID} not found")
    return pattern.sub(new_automation + "\n", content, count=1)


def patch_template_sensors() -> None:
    template_block = build_template_sensors()
    template_content = TEMPLATE_FILE.read_text(encoding="utf-8")
    if TEMPLATE_BEGIN in template_content:
        template_content = replace_marked_block(
            template_content, TEMPLATE_BEGIN, TEMPLATE_END, template_block
        )
    else:
        marker = "    # ---- Personer / hemma ---------------------------------------------------"
        if marker not in template_content:
            raise ValueError("Could not find insertion point in template.yaml")
        template_content = template_content.replace(
            marker,
            template_block + "\n\n" + marker,
            1,
        )
    TEMPLATE_FILE.write_text(template_content, encoding="utf-8")


def patch_files() -> None:
    patch_template_sensors()
    automation_block = build_automation()
    automations_content = AUTOMATIONS_FILE.read_text(encoding="utf-8")
    automations_content = replace_automation(automations_content, automation_block)
    AUTOMATIONS_FILE.write_text(automations_content, encoding="utf-8")


def patch_anna_files() -> None:
    patch_template_sensors()
    anna_block = build_anna_automation()
    automations_content = AUTOMATIONS_FILE.read_text(encoding="utf-8")
    automations_content = replace_anna_automation(automations_content, anna_block)
    AUTOMATIONS_FILE.write_text(automations_content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", action="store_true", help="Skriv template-sensorer till stdout")
    parser.add_argument("--automation", action="store_true", help="Skriv Ilias-automation till stdout")
    parser.add_argument("--anna-automation", action="store_true", help="Skriv Anna-automation till stdout")
    parser.add_argument("--patch", action="store_true", help="Uppdatera Ilias-automation och template-sensorer")
    parser.add_argument(
        "--patch-anna",
        action="store_true",
        help="Uppdatera Anna-automation och template-sensorer",
    )
    parser.add_argument(
        "--patch-all",
        action="store_true",
        help="Uppdatera template-sensorer samt Ilias- och Anna-automationer",
    )
    args = parser.parse_args()

    if args.patch_all:
        patch_template_sensors()
        automations_content = AUTOMATIONS_FILE.read_text(encoding="utf-8")
        automations_content = replace_automation(automations_content, build_automation())
        automations_content = replace_anna_automation(automations_content, build_anna_automation())
        AUTOMATIONS_FILE.write_text(automations_content, encoding="utf-8")
        print("Patched includes/template.yaml, Ilias automation and Anna automation", file=sys.stderr)
        return

    if args.patch:
        patch_files()
        print("Patched includes/template.yaml and Ilias automation", file=sys.stderr)
        return

    if args.patch_anna:
        patch_anna_files()
        print("Patched includes/template.yaml and Anna automation", file=sys.stderr)
        return

    if args.templates:
        print(build_template_sensors())
        return

    if args.automation:
        print(build_automation())
        return

    if args.anna_automation:
        print(build_anna_automation())
        return

    print(build_automation())


if __name__ == "__main__":
    main()
