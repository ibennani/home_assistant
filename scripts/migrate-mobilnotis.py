#!/usr/bin/env python3
"""Migrera notify.mobile_app_* och notify.foraldrar till script.mobilnotis."""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT / "automations.yaml", ROOT / "scripts.yaml"]


def _ha_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


yaml.SafeLoader.add_multi_constructor("!", _ha_tag)


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))

NOTIFY_SERVICES = re.compile(
    r"^notify\.(mobile_app_[\w]+|foraldrar|familjen)$"
)
NOTIFY_IN_TEMPLATE = re.compile(
    r"\bnotify\.(mobile_app_[\w]+|foraldrar|familjen)\b"
)


def determine_ikon(context: str, message: str) -> str:
    c = (context or "").lower()
    m = (message or "").lower()
    if "cursor" in c:
        return "cursor"
    if "husläge: till morgon" in c or "huslage till morgon" in m:
        return "huslage_morgon"
    if "husläge: till dag" in c or "huslage till dag" in m:
        return "huslage_dag"
    if "husläge: till kväll" in c or "huslage till kvall" in m or "huslage till kväll" in m:
        return "huslage_kvall"
    if "husläge: till natt" in c or "huslage till natt" in m:
        return "huslage_natt"
    if "vilka kommer hem" in c:
        return "zon"
    if any(
        token in c or token in m
        for token in (
            "diskmaskin",
            "tvättmaskin",
            "tvattmaskin",
            "luftavfuktare",
            "vitvaror",
        )
    ):
        return "vitvaror"
    return "standard"


def build_mobilnotis_data(
    mottagare: str,
    step_data: dict,
    context: str,
    *,
    mottagare_is_template: bool = False,
) -> dict:
    message = step_data.get("message", "")
    title = step_data.get("title", "")
    inner = step_data.get("data") or {}

    notis_data: dict = {}
    tag = ""
    vibration = ""

    for key, value in inner.items():
        if key in ("ttl", "priority"):
            continue
        if key == "tag":
            tag = value
        elif key == "vibration":
            vibration = value
        else:
            notis_data[key] = value

    ikon = determine_ikon(context, str(message))
    payload: dict = {"meddelande": message}
    if mottagare_is_template:
        payload["mottagare"] = mottagare
    else:
        payload["mottagare"] = mottagare
    if title:
        payload["title"] = title
    if ikon != "standard":
        payload["ikon"] = ikon
    if tag:
        payload["tag"] = tag
    if vibration:
        payload["vibration"] = vibration
    if notis_data:
        payload["notis_data"] = notis_data
    return payload


def make_mobilnotis_step(step: dict, payload: dict) -> dict:
    new_step = {"action": "script.mobilnotis", "data": payload}
    if "alias" in step:
        new_step["alias"] = step["alias"]
    return new_step


def convert_plain_notify(step: dict, context: str) -> dict | None:
    action = str(step.get("action", "")).strip()
    if not NOTIFY_SERVICES.match(action):
        return None
    mottagare = action.split(".", 1)[1]
    payload = build_mobilnotis_data(mottagare, step.get("data", {}), context)
    return make_mobilnotis_step(step, payload)


def convert_template_notify(step: dict, context: str) -> dict | list | None:
    action = str(step.get("action", "")).strip()
    if "notify." not in action or "{%" not in action:
        return None

    if "script.do_nothing" in action and re.search(r"\{%\s*if\s+", action):
        cond_match = re.search(r"\{%\s*if\s+(.*?)\s*%\}", action)
        if not cond_match:
            return None
        cond = cond_match.group(1).strip()
        mottagare_match = NOTIFY_IN_TEMPLATE.search(action)
        if not mottagare_match:
            return None
        mottagare = mottagare_match.group(1)
        payload = build_mobilnotis_data(
            mottagare, step.get("data", {}), context
        )
        return {
            "if": [
                {
                    "condition": "template",
                    "value_template": "{{ " + cond + " }}",
                }
            ],
            "then": [make_mobilnotis_step(step, payload)],
        }

    mottagare_template = NOTIFY_IN_TEMPLATE.sub(
        lambda m: m.group(1), action
    )
    mottagare_template = re.sub(
        r"\s*script\.do_nothing\s*", " ", mottagare_template
    ).strip()
    payload = build_mobilnotis_data(
        mottagare_template, step.get("data", {}), context
    )
    return make_mobilnotis_step(step, payload)


def convert_step(step: dict | list, context: str) -> dict | list:
    if isinstance(step, list):
        return [convert_step(item, context) for item in step]

    if not isinstance(step, dict):
        return step

    converted = convert_plain_notify(step, context)
    if converted is not None:
        return converted

    converted = convert_template_notify(step, context)
    if converted is not None:
        return converted

    new_step = deepcopy(step)
    for key in ("sequence", "then", "else"):
        if key in new_step and isinstance(new_step[key], list):
            new_step[key] = [
                convert_step(item, context) for item in new_step[key]
            ]
    if "choose" in new_step and isinstance(new_step["choose"], list):
        for branch in new_step["choose"]:
            if isinstance(branch, dict) and "sequence" in branch:
                branch["sequence"] = [
                    convert_step(item, context) for item in branch["sequence"]
                ]
    if "repeat" in new_step and isinstance(new_step["repeat"], dict):
        rep = new_step["repeat"]
        if "sequence" in rep:
            rep["sequence"] = [
                convert_step(item, context) for item in rep["sequence"]
            ]
    return new_step


def walk_automation(automation: dict) -> None:
    context = automation.get("alias") or automation.get("id") or ""
    if "action" in automation:
        automation["action"] = convert_step(automation["action"], context)
    if "actions" in automation:
        automation["actions"] = convert_step(automation["actions"], context)


def walk_script(script_id: str, script: dict) -> None:
    if script_id == "mobilnotis":
        return
    context = script.get("alias") or script_id
    if "sequence" in script:
        script["sequence"] = convert_step(script["sequence"], context)


def migrate_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    data = load_yaml(path)
    if data is None:
        return 0

    before = text.count("notify.mobile_app_") + text.count("notify.foraldrar")

    if path.name == "automations.yaml":
        for automation in data:
            if isinstance(automation, dict):
                walk_automation(automation)
    elif path.name == "scripts.yaml":
        for script_id, script in data.items():
            if isinstance(script, dict):
                walk_script(script_id, script)

    path.write_text(
        yaml.dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )
    after_text = path.read_text(encoding="utf-8")
    after = after_text.count("notify.mobile_app_") + after_text.count(
        "notify.foraldrar"
    )
    return before - after


def main() -> int:
    total = 0
    for path in TARGETS:
        changed = migrate_file(path)
        print(f"{path.name}: migrerade {changed} notify-anrop")
        total += changed
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
