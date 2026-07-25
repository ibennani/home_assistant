#!/usr/bin/env python3
"""Uppdatera Lovelace-dashboards: isabelles -> ilias (rum), behåll zoner."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from copy import deepcopy

try:
    import websockets
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

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
    ("isabelles_skrivbord", "ilias_skrivbord"),
    ("isabelles_myslampa", "ilias_myslampa"),
    ("isabelles_fonster", "ilias_fonster"),
    ("fjarr_isabelles_rum", "fjarr_ilias_rum"),
    ("isabelles_rum", "ilias_rum"),
]

DISPLAY_REPLACEMENTS = [
    ("Pucken i Isabelles rum", "Pucken i Ilias rum"),
    ("Belysning i Isabelles rum", "Belysning i Ilias rum"),
    ("Isabelles skrivbord", "Ilias skrivbord"),
    ("Isabelles fönster", "Ilias fönster"),
    ("Isabelles rum", "Ilias rum"),
]


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


def transform_value(value: str) -> str:
    if value.startswith("zone.isabelles_"):
        return value
    out = value
    for old, new in SLUG_REPLACEMENTS:
        out = out.replace(old, new)
    for old, new in DISPLAY_REPLACEMENTS:
        out = out.replace(old, new)
    return out


def transform_obj(obj):
    if isinstance(obj, str):
        return transform_value(obj)
    if isinstance(obj, list):
        return [transform_obj(i) for i in obj]
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            new_key = transform_value(k) if isinstance(k, str) else k
            new_dict[new_key] = transform_obj(v)
        return new_dict
    return obj


async def ws_call(ws, msg_id: int, payload: dict):
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

    async with websockets.connect(ws_url, max_size=32 * 1024 * 1024) as ws:
        assert json.loads(await ws.recv())["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
        assert json.loads(await ws.recv())["type"] == "auth_ok"

        dashboards = await ws_call(ws, 1, {"type": "lovelace/dashboards/list"})
        msg_id = 2
        updated = 0

        dash_list = dashboards if isinstance(dashboards, list) else dashboards.get("dashboards", [])
        for dash in dash_list:
            url_path = dash.get("url_path")
            if url_path is None:
                url_path = None  # default dashboard
            title = dash.get("title", url_path)
            try:
                config = await ws_call(
                    ws,
                    msg_id,
                    {"type": "lovelace/config", "url_path": url_path, "force": True},
                )
            except Exception as exc:  # noqa: BLE001
                print(f"SKIP {title}: {exc}")
                msg_id += 1
                continue
            msg_id += 1

            new_config = transform_obj(config)
            if new_config == config:
                print(f"UNCHANGED: {title}")
                continue

            await ws_call(
                ws,
                msg_id,
                {
                    "type": "lovelace/config/save",
                    "url_path": url_path,
                    "config": new_config,
                },
            )
            msg_id += 1
            updated += 1
            print(f"UPDATED: {title} ({url_path})")

        print(f"Done. dashboards_updated={updated}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
