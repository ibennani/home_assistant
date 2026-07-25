#!/usr/bin/env python3
"""Uppdatera Lovelace-dashboards: albins -> eriks (rum), behåll zoner."""
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

SLUG_REPLACEMENTS = [
    ("lights_taklamporna_i_albins_rum", "lights_taklamporna_i_eriks_rum"),
    ("albins_rum_temperatur_battery_2", "eriks_rum_temperatur_battery_2"),
    ("oversvamning_albins_fonster", "oversvamning_eriks_fonster"),
    ("hyllan_ovanfor_albins_sang", "hyllan_ovanfor_eriks_sang"),
    ("luftkvalitet_ppb_albins_rum", "luftkvalitet_ppb_eriks_rum"),
    ("luftkvalitet_albins_rum_pm25", "luftkvalitet_eriks_rum_pm25"),
    ("fjarr_2_albins_rum_battery", "fjarr_2_eriks_rum_battery"),
    ("rullgardin_albins_rum_batteri", "rullgardin_eriks_rum_batteri"),
    ("albins_rum_belysning", "eriks_rum_belysning"),
    ("taklampan_albins_fonster_level", "taklampan_eriks_fonster_level"),
    ("taklampan_albins_sang_level", "taklampan_eriks_sang_level"),
    ("albins_rum_luftfuktighet", "eriks_rum_luftfuktighet"),
    ("albins_rum_ljusstyrka", "eriks_rum_ljusstyrka"),
    ("albins_skrivbord_rorelse", "eriks_skrivbord_rorelse"),
    ("albins_rum_lufttryck", "eriks_rum_lufttryck"),
    ("albins_rum_rorelse_battery", "eriks_rum_rorelse_battery"),
    ("albins_rum_rorelse", "eriks_rum_rorelse"),
    ("googlehome_albins_rum", "googlehome_eriks_rum"),
    ("rullgardin_albins_rum", "rullgardin_eriks_rum"),
    ("fjarr_albins_rum_battery", "fjarr_eriks_rum_battery"),
    ("fjarr_albins_rum", "fjarr_eriks_rum"),
    ("albins_fonster_battery", "eriks_fonster_battery"),
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
    ("Albins garderob", "Eriks garderob"),
    ("Albins skrivbord", "Eriks skrivbord"),
    ("Albins fönster", "Eriks fönster"),
    ("Albins rum", "Eriks rum"),
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
    if value.startswith("zone.albins_"):
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
