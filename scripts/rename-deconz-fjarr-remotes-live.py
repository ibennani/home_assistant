#!/usr/bin/env python3
"""Byt namn på IKEA-fjärrar i deCONZ-bridgen efter rumsomdöpning.

Entity registry-byten (rename-*-entities-live.py) räcker inte: deconz_event
använder enhetens namn på bridgen som event-id (t.ex. fjarr_eriks_rum).
Kör detta skript efter entity registry-rename så automatiseringarna matchar igen.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (battery_entity_id, nytt deCONZ-namn, device_id, area_id)
REMOTE_RENAMES: list[tuple[str, str, str, str]] = [
    ("sensor.fjarr_eriks_rum_battery", "Fjärr Eriks rum", "f41fcbf9d68e6e1c1b4739f933a576e2", "eriks_rum"),
    ("sensor.fjarr_2_eriks_rum_battery", "Fjärr 2 Eriks rum", "bd29e339733b6aef285cbd3a2938b9d8", "eriks_rum"),
    ("sensor.fjarr_annas_rum_battery", "Fjärr Annas rum", "8cef7cd6e4b3b1ae0e42a1171ce0a939", "annas_rum"),
    ("sensor.fjarr_ilias_rum_battery", "Fjärr Ilias rum", "8ae42038832f58bfa6bfe2afc6e4c053", "ilias_rum"),
    (
        "sensor.fjarr_taklampan_i_ilias_rum_battery",
        "Fjärr taklampan i Ilias rum",
        "17a205a82f6a5f0a66137d21e100a1a0",
        "ilias_rum",
    ),
    (
        "sensor.fjarr_rullgardin_ilias_rum_batteri",
        "Fjärr rullgardin Ilias rum",
        "9f2735237e7459cd2794666c518dd7fd",
        "ilias_rum",
    ),
    (
        "sensor.fjarr_rullgardin_annas_rum_batteri",
        "Fjärr rullgardin Annas rum",
        "f1d71f8406e7329002ae104e860e6311",
        "annas_rum",
    ),
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


def call_service(ha_url: str, ha_token: str, domain: str, service: str, data: dict) -> None:
    payload = json.dumps({"domain": domain, "service": service, "service_data": data}).encode()
    req = urllib.request.Request(
        f"{ha_url}/api/services/{domain}/{service}",
        data=payload,
        headers={
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def ws_update_device(ws_url: str, ha_token: str, device_id: str, name: str, area_id: str, msg_id: int) -> int:
    import asyncio
    import websockets

    async def _run() -> None:
        async with websockets.connect(ws_url, max_size=4 * 1024 * 1024) as ws:
            hello = json.loads(await ws.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError(f"Unexpected hello: {hello}")
            await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                raise SystemExit(f"Auth failed: {auth}")
            await ws.send(
                json.dumps(
                    {
                        "id": msg_id,
                        "type": "config/device_registry/update",
                        "device_id": device_id,
                        "name_by_user": name,
                        "area_id": area_id,
                    }
                )
            )
            result = json.loads(await ws.recv())
            if not result.get("success", True):
                raise RuntimeError(result)

    asyncio.run(_run())
    return msg_id + 1


def main() -> int:
    ha_url, ha_token = load_ha_creds()
    ws_url = ha_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"
    errors: list[str] = []
    msg_id = 1

    for entity_id, new_name, device_id, area_id in REMOTE_RENAMES:
        try:
            call_service(
                ha_url,
                ha_token,
                "deconz",
                "configure",
                {"entity": entity_id, "data": {"name": new_name}},
            )
            print(f"DECONZ {entity_id} -> {new_name!r}")
        except urllib.error.HTTPError as exc:
            errors.append(f"deconz {entity_id}: HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"deconz {entity_id}: {exc}")
            continue

        try:
            msg_id = ws_update_device(ws_url, ha_token, device_id, new_name, area_id, msg_id)
            print(f"DEVICE {device_id} -> {new_name!r} ({area_id})")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"device {device_id}: {exc}")

    print(f"\nDone: {len(REMOTE_RENAMES) - len(errors)}/{len(REMOTE_RENAMES)} OK, errors={len(errors)}")
    for err in errors:
        print(f"ERROR: {err}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
