#!/usr/bin/env python3
"""Migrera area_id isabelles_rum -> ilias_rum i HA."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

try:
    import websockets
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

OLD_AREA = "isabelles_rum"
NEW_AREA = "ilias_rum"
AREA_NAME = "Ilias rum"
AREA_ALIASES = ["Ilias rum", "Ilias"]


def load_ha_creds() -> tuple[str, str]:
    ha_url = os.environ.get("HA_URL", "").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN", "")
    if not ha_url or not ha_token:
        for key, val in os.environ.items():
            if re.match(r"^https://.*\.ui\.nabu\.casa/?$", key):
                ha_url = key.rstrip("/")
                ha_token = val
                break
    if not ha_url or not ha_token:
        raise SystemExit("HA_URL/HA_TOKEN saknas")
    return ha_url, ha_token


async def ws_call(ws, msg_id: int, payload: dict) -> dict:
    payload = {"id": msg_id, **payload}
    await ws.send(json.dumps(payload))
    while True:
        data = json.loads(await ws.recv())
        if data.get("id") == msg_id:
            if not data.get("success", True):
                raise RuntimeError(data)
            return data.get("result", data)


async def main() -> int:
    ha_url, ha_token = load_ha_creds()
    ws_url = ha_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"

    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024) as ws:
        assert json.loads(await ws.recv())["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
        assert json.loads(await ws.recv())["type"] == "auth_ok"

        msg_id = 1
        areas = await ws_call(ws, msg_id, {"type": "config/area_registry/list"})
        msg_id += 1

        area_ids = {a["area_id"] for a in areas}
        if NEW_AREA in area_ids and OLD_AREA not in area_ids:
            print(f"Area {NEW_AREA} finns redan och {OLD_AREA} saknas — inget att göra.")
            return 0
        if OLD_AREA not in area_ids:
            raise SystemExit(f"Käll-area {OLD_AREA} hittades inte")

        old_area = next(a for a in areas if a["area_id"] == OLD_AREA)
        aliases = list(dict.fromkeys([*AREA_ALIASES, *old_area.get("aliases", [])]))

        if NEW_AREA not in area_ids:
            # Frigör namnet genom tillfällig rename (namnet "Ilias rum" sitter på gamla arean)
            await ws_call(
                ws,
                msg_id,
                {
                    "type": "config/area_registry/update",
                    "area_id": OLD_AREA,
                    "name": "_migrate_isabelles_rum",
                    "aliases": [],
                },
            )
            msg_id += 1

            created = await ws_call(
                ws,
                msg_id,
                {
                    "type": "config/area_registry/create",
                    "name": AREA_NAME,
                    "aliases": aliases,
                },
            )
            msg_id += 1
            target_area = created.get("area_id")
            if not target_area:
                areas = await ws_call(ws, msg_id, {"type": "config/area_registry/list"})
                msg_id += 1
                created_row = next(
                    (a for a in areas if a["area_id"] not in {OLD_AREA} and a["name"] == AREA_NAME),
                    None,
                )
                if not created_row:
                    raise RuntimeError("Kunde inte skapa ny area")
                target_area = created_row["area_id"]
            print(f"CREATED area {target_area}")
        else:
            target_area = NEW_AREA
            await ws_call(
                ws,
                msg_id,
                {
                    "type": "config/area_registry/update",
                    "area_id": target_area,
                    "name": AREA_NAME,
                    "aliases": aliases,
                },
            )
            msg_id += 1
            print(f"UPDATED existing area {target_area}")

        entities = await ws_call(ws, msg_id, {"type": "config/entity_registry/list"})
        msg_id += 1
        devices = await ws_call(ws, msg_id, {"type": "config/device_registry/list"})
        msg_id += 1

        entity_updates = 0
        for entry in entities:
            if entry.get("area_id") == OLD_AREA:
                await ws_call(
                    ws,
                    msg_id,
                    {
                        "type": "config/entity_registry/update",
                        "entity_id": entry["entity_id"],
                        "area_id": target_area,
                    },
                )
                msg_id += 1
                entity_updates += 1

        device_updates = 0
        for dev in devices:
            if dev.get("area_id") == OLD_AREA:
                await ws_call(
                    ws,
                    msg_id,
                    {
                        "type": "config/device_registry/update",
                        "device_id": dev["id"],
                        "area_id": target_area,
                    },
                )
                msg_id += 1
                device_updates += 1

        await ws_call(
            ws,
            msg_id,
            {"type": "config/area_registry/delete", "area_id": OLD_AREA},
        )
        msg_id += 1

        print(
            f"Done: target_area={target_area}, entities_moved={entity_updates}, "
            f"devices_moved={device_updates}, deleted={OLD_AREA}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
