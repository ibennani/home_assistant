#!/usr/bin/env python3
"""Hämtar aktiva DHCP-leases från EdgeRouter.

Läser edgerouter_host, edgerouter_username och edgerouter_password
från /config/secrets.yaml. Utan giltiga uppgifter returneras tom lista.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

INFRA_MACS = {
    "f0:9f:c2:64:3d:cc",
    "02:42:c0:a8:00:0a",
    "02:42:c0:a8:00:0b",
    "3c:e1:a1:b4:29:f4",
}
PLACEHOLDER_VALUES = {"", "BYT_UT", "byt_ut"}


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


def normalize_mac(mac: str) -> str:
    return mac.strip().lower()


def empty_payload() -> None:
    print(json.dumps({"count": 0, "data": []}))


def login_and_fetch(host: str, username: str, password: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    login_data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode()
    login_req = urllib.request.Request(
        f"https://{host}/",
        data=login_data,
        method="POST",
    )
    opener.open(login_req, timeout=15, context=ctx)

    leases_req = urllib.request.Request(
        f"https://{host}/api/edge/data.json?data=dhcp_leases"
    )
    with opener.open(leases_req, timeout=20, context=ctx) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_leases(payload: dict) -> list[dict]:
    leases = payload.get("dhcp_leases", {}).get("lease", [])
    if isinstance(leases, dict):
        leases = [leases]

    clients: list[dict] = []
    now = int(time.time())

    for lease in leases:
        if str(lease.get("active", "0")) != "1":
            continue
        mac = normalize_mac(str(lease.get("mac", "")))
        if not mac or mac in INFRA_MACS:
            continue
        expires = int(lease.get("expires", 0) or 0)
        if expires and expires < now:
            continue
        hostname = str(lease.get("hostname", "") or "").strip()
        ip = str(lease.get("ip", "") or "").strip()
        if not ip:
            continue
        clients.append(
            {
                "mac": mac,
                "ip": ip,
                "hostname": hostname,
                "expires": expires,
            }
        )

    clients.sort(key=lambda item: (item.get("hostname") or item["ip"]).lower())
    return clients


def main() -> None:
    secrets = load_secrets()
    host = secrets.get("edgerouter_host", "192.168.0.1")
    username = secrets.get("edgerouter_username", "")
    password = secrets.get("edgerouter_password", "")

    if username in PLACEHOLDER_VALUES or password in PLACEHOLDER_VALUES:
        empty_payload()
        return

    try:
        payload = login_and_fetch(host, username, password)
        clients = parse_leases(payload)
        print(json.dumps({"count": len(clients), "data": clients}))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        json.JSONDecodeError,
        TimeoutError,
        OSError,
        KeyError,
        ValueError,
    ):
        empty_payload()


if __name__ == "__main__":
    main()
