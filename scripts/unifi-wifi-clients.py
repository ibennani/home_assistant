#!/usr/bin/env python3
"""Hämtar anslutna Wi-Fi-klienter från UniFi Network API.

Läser unifi_api_url och unifi_api_key från /config/secrets.yaml.
Utan giltig nyckel returneras tom lista (template-sensorer faller tillbaka).
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ALLOWED_SSIDS = {"Bennani", "Bennani_Guest", "2FarAway"}
INFRA_MACS = {
    "f0:9f:c2:64:3d:cc",
    "02:42:c0:a8:00:0a",
    "02:42:c0:a8:00:0b",
    "3c:e1:a1:b4:29:f4",
}
DEFAULT_URL = "https://192.168.0.1/proxy/network/api/s/default/stat/sta"
PLACEHOLDER_KEYS = {"", "BYT_UT", "byt_ut"}


def load_secrets() -> dict[str, str]:
    path = Path("/config/secrets.yaml")
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-zA-Z0-9_]+)\s*:\s*(.+?)\s*$", line.strip())
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        elif raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        values[key] = raw
    return values


def empty_payload() -> None:
    print(json.dumps({"count": 0, "data": []}))


def main() -> None:
    secrets = load_secrets()
    api_key = secrets.get("unifi_api_key", "")
    api_url = secrets.get("unifi_api_url", DEFAULT_URL)

    if api_key in PLACEHOLDER_KEYS:
        empty_payload()
        return

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    request = urllib.request.Request(
        api_url,
        headers={"X-API-KEY": api_key, "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, context=ctx, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        empty_payload()
        return

    clients = []
    for client in payload.get("data", []):
        if client.get("is_wired"):
            continue
        if client.get("essid") not in ALLOWED_SSIDS:
            continue
        mac = (client.get("mac") or "").lower()
        if mac in INFRA_MACS:
            continue
        clients.append(client)

    clients.sort(key=lambda item: item.get("uptime", 0))
    print(json.dumps({"count": len(clients), "data": clients}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        empty_payload()
        sys.exit(0)
