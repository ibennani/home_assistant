#!/usr/bin/env python3
"""Byt entity_id i HA entity registry för rumsrelaterade isabelles-* entiteter."""
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
    ("isabelles_rum_stall_in_belysningen", "ilias_rum_stall_in_belysningen"),
    ("isabelles_rum_kontrollera_belysningen_logiken", "ilias_rum_kontrollera_belysningen_logiken"),
    ("isabelles_rum_styr_taklampan", "ilias_rum_styr_taklampan"),
    ("input_boolean_isabelles_rum", "input_boolean_ilias_rum"),
    ("isabelles_skrivbord", "ilias_skrivbord"),
    ("isabelles_myslampa", "ilias_myslampa"),
    ("isabelles_fonster", "ilias_fonster"),
    ("fjarr_isabelles_rum", "fjarr_ilias_rum"),
    ("isabeles_taklampa", "ilias_taklampa"),
    ("isabelles_rum", "ilias_rum"),
]

DISPLAY_REPLACEMENTS = [
    ("Pucken i Isabelles rum", "Pucken i Ilias rum"),
    ("Belysning i Isabelles rum", "Belysning i Ilias rum"),
    ("GH Isabelles rum", "GH Ilias rum"),
    ("Dimma Isabelles taklampa", "Dimma Ilias taklampa"),
    ("Lamporna ovanför Isabelles säng", "Lamporna ovanför Ilias säng"),
    ("Lamporna i Isabelles fönster", "Lamporna i Ilias fönster"),
    ("Isabelles myslampa", "Ilias myslampa"),
    ("Isabelles skrivbord", "Ilias skrivbord"),
    ("Isabelles fönster", "Ilias fönster"),
    ("Isabelles taklampa", "Ilias taklampa"),
    ("i Isabelles rum", "i Ilias rum"),
    ("Isabelles rum", "Ilias rum"),
    ("Isabbelles rum", "Ilias rum"),
    ("Fjärr Isabelles rum", "Fjärr Ilias rum"),
]

SKIP_ENTITY_PATTERNS = [
    re.compile(r"^zone\.isabelles_"),
    re.compile(r"^person\.isabelle"),
    re.compile(r"^device_tracker\.annelies_iphone$"),
    re.compile(r"^sensor\.hp_color_laserjet"),
    re.compile(r"^update\.krisinfo"),
]

ROOM_ENTITY_PATTERNS = [
    re.compile(r"isabelles"),
    re.compile(r"isabeles"),
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
    if name and ("Isabelles rum" in name or "Isabelles fönster" in name or "Isabelles säng" in name or "Isabelles myslampa" in name or "Isabelles skrivbord" in name or "Taklampan i Isabelles" in name):
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

        # Först entity_id-byten (slug i entity_id)
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

        # Uppdatera listan efter rename
        entries = await ws_call(ws, msg_id, {"type": "config/entity_registry/list"})
        msg_id += 1

        # Sedan visningsnamn
        for entry in entries:
            entity_id = entry["entity_id"]
            current_name = entry.get("name")
            original_name = entry.get("original_name") or ""
            base = current_name if current_name else original_name
            if not should_process_entity(entity_id, base):
                continue
            new_name = transform_name(base)
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
