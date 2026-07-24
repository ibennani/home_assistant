#!/usr/bin/env python3
"""Generera Mobilnotis Ilias-automation med zone.entered/zone.left."""

import textwrap

TRACKED_ENTITIES = [
    "person.anna_bennani",
    "device_tracker.albins_iphone_12_gps_tracker",
    "device_tracker.annelies_iphone",
    "device_tracker.erik_s23",
    "device_tracker.ulrikas_iphone",
    "device_tracker.jockesiphone",
    "device_tracker.mariesiphone",
    "device_tracker.android56cbe288b1a113c8",
    "device_tracker.youssef_honor_8",
    "device_tracker.zaksiphone",
    "device_tracker.safiabennani",
    "device_tracker.78521aac945e",
    "device_tracker.84c7ea28ca07",
    "device_tracker.adinas_iphone",
    "device_tracker.hannas_iphone_7",
    "device_tracker.marias_iphone",
]

ZONES = [
    ("zone.home", "home"),
    ("zone.annas_jobb", "annas_jobb"),
    ("zone.eriks_skola", "eriks_skola"),
    ("zone.ilias_jobb", "ilias_jobb"),
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
    ("zone.molndahls_sjukhus", "molndahls_sjukhus"),
    ("zone.stefan", "stefan"),
    ("zone.elins_jobb", "elins_jobb"),
]

# Jinja-meddelanden per zon (entered / left) – från befintlig automation.
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
    "kth_campus": {
        "entered": "{{ person }} {% if person == 'Albin' %}är på KTH {% else %}är på KTH{% endif %}",
        "left": "{{ person }} {% if person == 'Albin' %}har lämnat KTH {% else %}har lämnat KTH{% endif %}",
    },
    "kth_flemmingsberg": {
        "entered": "{{ person }} är på Youssef och Emma",
        "left": "{{ person }} har lämnat Youssef och Emma",
    },
    "albins_mamma": {
        "entered": "{{ person }} {% if person == 'Albin' %}är hos mamma {% else %}är hos Albins mamma{% endif %}",
        "left": "{{ person }} {% if person == 'Albin' %}har åkt hemifrån mamma {% else %}har åkt ifrån Albins mamma{% endif %}",
    },
    "isabelles_jobb": {
        "entered": "{{ person }} {% if person == 'Isabelle' %}är på jobbet {% else %}är på Isabelles jobb{% endif %}",
        "left": "{{ person }} {% if person == 'Isabelle' %}har lämnat jobbet {% else %}har lämnat Isabelles jobb{% endif %}",
    },
    "albin": {
        "entered": "{{ person }} {% if person == 'Albin' %}är i sitt hem {% else %}är hemma hos Albin{% endif %}",
        "left": "{{ person }} {% if person == 'Albin' %}har lämnat sitt hem {% else %}har åkt hemifrån Albin{% endif %}",
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
        "left": "{{ person }} har lämnat Mölndahls sjukhus",
    },
    "stefan": {
        "entered": "{{ person }} är hos Stefan",
        "left": "{{ person }} har åkt ifrån Stefan",
    },
    "elins_jobb": {
        "entered": "{{ person }} är på Elins jobb",
        "left": "{{ person }} har lämnat Elins jobb",
    },
}


def indent_block(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line else line for line in text.splitlines())


def build_triggers() -> str:
    lines = []
    for zone_entity, slug in ZONES:
        lines.append(f"  - trigger: zone.entered")
        lines.append(f"    id: entered_{slug}")
        lines.append(f"    target:")
        lines.append(f"      entity_id:")
        for ent in TRACKED_ENTITIES:
            lines.append(f"      - {ent}")
        lines.append(f"    options:")
        lines.append(f"      zone: {zone_entity}")
        lines.append(f"  - trigger: zone.left")
        lines.append(f"    id: left_{slug}")
        lines.append(f"    target:")
        lines.append(f"      entity_id:")
        for ent in TRACKED_ENTITIES:
            lines.append(f"      - {ent}")
        lines.append(f"    options:")
        lines.append(f"      zone: {zone_entity}")
    return "\n".join(lines)


def build_message_template() -> str:
    person_map = textwrap.dedent(
        """\
        {%- if trigger.entity_id == 'person.anna_bennani' -%}
          {%- set person = 'Anna' -%}
        {%- elif trigger.entity_id == 'device_tracker.albins_iphone_12_gps_tracker' -%}
          {%- set person = 'Albin' -%}
        {%- elif trigger.entity_id == 'device_tracker.annelies_iphone' -%}
          {%- set person = 'Isabelle' -%}
        {%- elif trigger.entity_id == 'device_tracker.erik_s23' -%}
          {%- set person = 'Erik' -%}
        {%- elif trigger.entity_id == 'device_tracker.ulrikas_iphone' -%}
          {%- set person = 'Ulrika' -%}
        {%- elif trigger.entity_id == 'device_tracker.jockesiphone' -%}
          {%- set person = 'Jocke' -%}
        {%- elif trigger.entity_id == 'device_tracker.mariesiphone' -%}
          {%- set person = 'Mie' -%}
        {%- elif trigger.entity_id == 'device_tracker.android56cbe288b1a113c8' -%}
          {%- set person = 'Elin' -%}
        {%- elif trigger.entity_id == 'device_tracker.youssef_honor_8' -%}
          {%- set person = 'Youssef' -%}
        {%- elif trigger.entity_id == 'device_tracker.zaksiphone' -%}
          {%- set person = 'Zaki' -%}
        {%- elif trigger.entity_id == 'device_tracker.safiabennani' -%}
          {%- set person = 'Safia' -%}
        {%- elif trigger.entity_id == 'device_tracker.78521aac945e' -%}
          {%- set person = 'Solveig' -%}
        {%- elif trigger.entity_id == 'device_tracker.84c7ea28ca07' -%}
          {%- set person = 'Sarah' -%}
        {%- elif trigger.entity_id == 'device_tracker.adinas_iphone' -%}
          {%- set person = 'Adina' -%}
        {%- elif trigger.entity_id == 'device_tracker.hannas_iphone_7' -%}
          {%- set person = 'Hanna' -%}
        {%- elif trigger.entity_id == 'device_tracker.marias_iphone' -%}
          {%- set person = 'Maria' -%}
        {%- else -%}
          {%- set person = 'Okänd' -%}
        {%- endif -%}
        {%- if trigger.id.startswith('entered_') -%}
          {%- set event = 'entered' -%}
          {%- set zone_slug = trigger.id[8:] -%}
        {%- else -%}
          {%- set event = 'left' -%}
          {%- set zone_slug = trigger.id[5:] -%}
        {%- endif -%}"""
    )

    branches = []
    for slug in ZONE_MESSAGES:
        entered = ZONE_MESSAGES[slug]["entered"]
        left = ZONE_MESSAGES[slug]["left"]
        branches.append(
            f"        {{%- elif zone_slug == '{slug}' and event == 'entered' -%}}\n"
            f"          {entered}\n"
            f"        {{%- elif zone_slug == '{slug}' and event == 'left' -%}}\n"
            f"          {left}"
        )

    body = person_map + "\n" + "\n".join(branches)
    body += "\n        {%- else -%}\n          {{ person }} zonhändelse ({{ zone_slug }}/{{ event }})\n        {%- endif -%}"
    # Fix first branch from elif to if
    body = body.replace("        {%- elif zone_slug ==", "        {%- if zone_slug ==", 1)
    return "HEMMET {{ now().strftime('%R') }}: \n" + body


def build_automation() -> str:
    message = build_message_template()
    lines = [
        "- id: '7918348674111555999'",
        "  alias: 'Mobilnotis Ilias: Vilka kommer hem och går hemifrån'",
        "  mode: parallel",
        "  triggers:",
        build_triggers(),
        "  actions:",
        "  - variables:",
        "      zone_slug: >-",
        "        {% if trigger.id.startswith('entered_') %}{{ trigger.id[8:] }}{% else %}{{ trigger.id[5:] }}{% endif %}",
        "      is_left: \"{{ trigger.id.startswith('left_') }}\"",
        "  - if:",
        "    - condition: template",
        "      value_template: \"{{ is_left }}\"",
        "    then:",
        "    - delay:",
        "        seconds: 5",
        "    - condition: template",
        "      value_template: \"{{ state_attr(trigger.entity_id, 'in_zones') | default([], true) | length == 0 }}\"",
        "  - variables:",
        "      notification_message: >",
    ]
    for line in message.splitlines():
        lines.append(f"        {line}")
    lines += [
        "  - action: notify.mobile_app_ilias_s23_ultra",
        "    data:",
        "      message: \"{{ notification_message }}\"",
        "      data:",
        "        ttl: 0",
        "        priority: high",
        "  - action: homeassistant.update_entity",
        "    entity_id: sensor.people_home_count",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_automation())
