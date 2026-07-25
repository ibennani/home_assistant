#!/usr/bin/env python3
"""Uppdatera Lovelace-dashboards: eriks -> annas (rum), behåll zoner."""
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
    ("settings_rullgardiner_eriks_rum_elevation_ner", "settings_rullgardiner_annas_rum_elevation_ner"),
    ("settings_rullgardiner_eriks_rum_azimuth_upp", "settings_rullgardiner_annas_rum_azimuth_upp"),
    ("eriks_rum_skrivbord_rorelse_battery", "annas_rum_skrivbord_rorelse_battery"),
    ("eriks_rum_rorelse_battery_2", "annas_rum_rorelse_battery_2"),
    ("eriks_rum_temperatur_battery", "annas_rum_temperatur_battery"),
    ("fjarr_rullgardin_eriks_rum_batteri", "fjarr_rullgardin_annas_rum_batteri"),
    ("luftkvalitet_eriks_rum_pm25", "luftkvalitet_annas_rum_pm25"),
    ("luftkvalitet_eriks_rum_ppb", "luftkvalitet_annas_rum_ppb"),
    ("rullgardin_eriks_rum_batteri", "rullgardin_annas_rum_batteri"),
    ("eriks_myshorna_nattljusstyrka", "annas_myshorna_nattljusstyrka"),
    ("eriks_myshorna_nattljus_tid", "annas_myshorna_nattljus_tid"),
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
    ("eriks_fonster_battery", "annas_fonster_battery"),
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
    ("Eriks myshörna", "Annas myshörna"),
    ("Eriks myshöna", "Annas myshörna"),
    ("Eriks skrivbord", "Annas skrivbord"),
    ("Eriks fönster", "Annas fönster"),
    ("Eriks rum", "Annas rum"),
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
    if value.startswith("zone.eriks_"):
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
                url_path = None
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
