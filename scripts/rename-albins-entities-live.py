#!/usr/bin/env python3
"""Byt entity_id i HA entity registry för rumsrelaterade albins-* entiteter."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

ROOT = Path(__file__).resolve().parents[1]

SLUG_REPLACEMENTS = [
    ("lights_taklamporna_i_albins_rum", "lights_taklamporna_i_eriks_rum"),
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
    ("Taklamporna i Albins rum", "Taklamporna i Eriks rum"),
    ("Pucken i Albins rum", "Pucken i Eriks rum"),
    ("Belysning i Albins rum", "Belysning i Eriks rum"),
    ("GH Albins rum", "GH Eriks rum"),
    ("Albins garderob", "Eriks garderob"),
    ("Albins skrivbord", "Eriks skrivbord"),
    ("Albins fönster", "Eriks fönster"),
    ("Albins stereo", "Eriks stereo"),
    ("Albins myslampa", "Eriks myslampa"),
    ("Taklampan ovanför Albins fönster", "Taklampan ovanför Eriks fönster"),
    ("Taklampan ovanför Albins säng", "Taklampan ovanför Eriks säng"),
    ("i Albins rum", "i Eriks rum"),
    ("Albins rum", "Eriks rum"),
    ("Fjärr Albins rum", "Fjärr Eriks rum"),
]

SKIP_ENTITY_PATTERNS = [
    re.compile(r"^zone\.albins_"),
    re.compile(r"^person\.albin"),
    re.compile(r"^device_tracker\.albins_iphone_12_gps_tracker$"),
    re.compile(r"^device_tracker\.albins_dell_16_2$"),
]

ROOM_ENTITY_PATTERNS = [
    re.compile(r"albins_rum"),
    re.compile(r"albins_myslampa"),
    re.compile(r"albins_fonster"),
    re.compile(r"albins_garderob"),
    re.compile(r"albins_biosalong"),
    re.compile(r"albins_stereo"),
    re.compile(r"albins_skrivbord"),
    re.compile(r"albins_flakt"),
    re.compile(r"albins_tv"),
    re.compile(r"googlehome_albins"),
    re.compile(r"fjarr_albins"),
    re.compile(r"fjarr_2_albins"),
    re.compile(r"rullgardin_albins"),
    re.compile(r"taklampan_albins"),
    re.compile(r"albins_lavalampa"),
    re.compile(r"hyllan_ovanfor_albins"),
    re.compile(r"oversvamning_albins"),
    re.compile(r"luftkvalitet_.*albins"),
    re.compile(r"lights_taklamporna_i_albins"),
]


def load_ha_creds() -> tuple[str, str]:
    ha_url = os.environ.get("HA_URL", "").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN", "")
    if ha_url and ha_token:
        return ha_url, ha_token
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("HA_URL="):
                ha_url = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            elif line.startswith("HA_TOKEN="):
                ha_token = line.split("=", 1)[1].strip().strip('"')
    if not ha_url or not ha_token:
        for key, val in os.environ.items():
            if re.match(r"^https://.*\.ui\.nabu\.casa/?$", key):
                ha_url = key.rstrip("/")
                ha_token = val
                break
    if not ha_url or not ha_token:
        raise SystemExit("HA_URL/HA_TOKEN saknas")
    return ha_url, ha_token


def transform_slug(slug: str) -> str:
    out = slug
    for old, new in SLUG_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def transform_name(name: str) -> str:
    out = name
    for old, new in DISPLAY_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def should_process_entity(entity_id: str, name: str | None) -> bool:
    if any(p.search(entity_id) for p in SKIP_ENTITY_PATTERNS):
        return False
    if any(p.search(entity_id) for p in ROOM_ENTITY_PATTERNS):
        return True
    if name and (
        "Albins rum" in name
        or "Albins fönster" in name
        or "Albins garderob" in name
        or "Albins skrivbord" in name
        or "Albins stereo" in name
        or "Albins myslampa" in name
        or "Pucken i Albins" in name
        or "Taklampan" in name and "Albins" in name
        or "Taklamporna i Albins" in name
        or "översvamning Albins" in name.lower()
    ):
        return True
    return False


async def ws_call(ws, msg_id: int, payload: dict) -> dict:
    payload = {"id": msg_id, **payload}
    await ws.send(json.dumps(payload))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get("id") == msg_id:
            if not data.get("success", True):
                raise RuntimeError(data)
            return data.get("result", data)


async def main() -> int:
    ha_url, ha_token = load_ha_creds()
    ws_url = ha_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"

    renamed = 0
    named = 0
    skipped = 0
    errors: list[str] = []

    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected hello: {hello}")
        await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
        auth = json.loads(await ws.recv())
        if auth.get("type") != "auth_ok":
            raise SystemExit(f"Auth failed: {auth}")

        entries = await ws_call(ws, 1, {"type": "config/entity_registry/list"})
        msg_id = 2

        for entry in entries:
            entity_id = entry["entity_id"]
            if not should_process_entity(entity_id, entry.get("name") or entry.get("original_name")):
                continue
            domain, slug = entity_id.split(".", 1)
            new_slug = transform_slug(slug)
            if new_slug == slug:
                continue
            new_entity_id = f"{domain}.{new_slug}"
            try:
                await ws_call(
                    ws,
                    msg_id,
                    {
                        "type": "config/entity_registry/update",
                        "entity_id": entity_id,
                        "new_entity_id": new_entity_id,
                    },
                )
                renamed += 1
                print(f"RENAMED {entity_id} -> {new_entity_id}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{entity_id}: {exc}")
            msg_id += 1

        entries = await ws_call(ws, msg_id, {"type": "config/entity_registry/list"})
        msg_id += 1

        for entry in entries:
            entity_id = entry["entity_id"]
            current_name = entry.get("name")
            original_name = entry.get("original_name") or ""
            base = current_name if current_name else original_name
            alt = original_name if current_name else ""
            if not should_process_entity(entity_id, base) and not should_process_entity(entity_id, alt):
                continue
            new_name = transform_name(base)
            if new_name == base and alt:
                new_name = transform_name(alt)
                base = alt
            if new_name == base:
                skipped += 1
                continue
            try:
                await ws_call(
                    ws,
                    msg_id,
                    {
                        "type": "config/entity_registry/update",
                        "entity_id": entity_id,
                        "name": new_name,
                    },
                )
                named += 1
                print(f"NAMED {entity_id}: {base!r} -> {new_name!r}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"name {entity_id}: {exc}")
            msg_id += 1

    print(f"\nDone: renamed={renamed}, named={named}, skipped={skipped}, errors={len(errors)}")
    for err in errors[:20]:
        print(f"ERROR: {err}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
