#!/usr/bin/env python3
"""Exportera ett Lovelace-dashboard från live HA till YAML i repot."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

try:
    import websockets
    import yaml
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "pyyaml", "-q"])
    import websockets
    import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dashboards" / "dashboard-september-2025.yaml"


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


async def ws_call(ws, msg_id: int, payload: dict):
    payload = {"id": msg_id, **payload}
    await ws.send(json.dumps(payload))
    while True:
        data = json.loads(await ws.recv())
        if data.get("id") == msg_id:
            if not data.get("success", True):
                raise RuntimeError(data)
            return data.get("result", data)


async def fetch_dashboard(url_path: str) -> dict:
    ha_url, ha_token = load_ha_creds()
    ws_url = ha_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"

    async with websockets.connect(ws_url, max_size=32 * 1024 * 1024) as ws:
        assert json.loads(await ws.recv())["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": ha_token}))
        assert json.loads(await ws.recv())["type"] == "auth_ok"
        return await ws_call(
            ws,
            1,
            {"type": "lovelace/config", "url_path": url_path, "force": True},
        )


def dump_dashboard_yaml(config: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Översikt (dashboard-september-2025)\n"
        "# Exporterad från live Home Assistant. Redigera här och synka via git.\n"
        "# Exportera om från HA: python3 scripts/export-dashboard-from-ha.py\n\n"
    )
    body = yaml.dump(
        config,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    output.write_text(header + body, encoding="utf-8")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url-path",
        default="dashboard-september-2025",
        help="Dashboard url_path i HA (default: dashboard-september-2025)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Utfil (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    args = parser.parse_args()

    config = await fetch_dashboard(args.url_path)
    dump_dashboard_yaml(config, args.output)
    views = len(config.get("views", []))
    print(f"Exporterade {args.url_path} -> {args.output} ({views} vyer)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
