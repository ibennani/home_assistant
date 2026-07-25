#!/usr/bin/env python3
"""Byt entity_id i HA entity registry för rumsrelaterade eriks-* entiteter."""
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
    ("settings_rullgardiner_eriks_rum_elevation_ner", "settings_rullgardiner_annas_rum_elevation_ner"),
    ("settings_rullgardiner_eriks_rum_azimuth_upp", "settings_rullgardiner_annas_rum_azimuth_upp"),
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
    ("Pucken i Eriks rum", "Pucken i Annas rum"),
    ("Belysning i Eriks rum", "Belysning i Annas rum"),
    ("GH Eriks rum", "GH Annas rum"),
    ("Brandvarnaren i Eriks rum", "Brandvarnaren i Annas rum"),
    ("Skrivbordet i Eriks rum", "Skrivbordet i Annas rum"),
    ("Taklampan i Eriks rum", "Taklampan i Annas rum"),
    ("Lampan i Eriks fönster", "Lampan i Annas fönster"),
    ("Eriks rum skrivbord rörelse", "Annas rum skrivbord rörelse"),
    ("Eriks rum rörelse", "Annas rum rörelse"),
    ("Eriks myshörna", "Annas myshörna"),
    ("Eriks myshöna", "Annas myshörna"),
    ("Eriks skrivbord", "Annas skrivbord"),
    ("Eriks fönster", "Annas fönster"),
    ("Eriks stereo", "Annas stereo"),
    ("i Eriks rum", "i Annas rum"),
    ("Eriks rum", "Annas rum"),
    ("Fjärr Eriks rum", "Fjärr Annas rum"),
]

SKIP_ENTITY_PATTERNS = [
    re.compile(r"^zone\.eriks_"),
    re.compile(r"^person\.erik"),
    re.compile(r"^device_tracker\.erik_s23$"),
]

ROOM_ENTITY_PATTERNS = [
    re.compile(r"eriks_rum"),
    re.compile(r"eriks_myshorna"),
    re.compile(r"eriks_fonster"),
    re.compile(r"eriks_jordglob"),
    re.compile(r"eriks_stereo"),
    re.compile(r"eriks_skrivbord"),
    re.compile(r"eriks_byra"),
    re.compile(r"googlehome_eriks"),
    re.compile(r"fjarr_eriks"),
    re.compile(r"fjarr_rullgardin_eriks"),
    re.compile(r"rullgardin_eriks"),
    re.compile(r"taklampan_eriks"),
    re.compile(r"lampa_eriks"),
    re.compile(r"lampan_i_eriks"),
    re.compile(r"led_under_eriks"),
    re.compile(r"luftkvalitet_eriks"),
    re.compile(r"settings_rullgardiner_eriks"),
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
        "Eriks rum" in name
        or "Eriks fönster" in name
        or "Eriks myshörna" in name
        or "Eriks myshöna" in name
        or "Eriks skrivbord" in name
        or "Eriks stereo" in name
        or "Pucken i Eriks" in name
        or "Taklampan i Eriks" in name
        or "Brandvarnaren i Eriks" in name
        or "Skrivbordet i Eriks" in name
        or "Rullgardinen i Eriks" in name
        or "Lampan i Eriks" in name
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
