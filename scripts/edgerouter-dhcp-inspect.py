#!/usr/bin/env python3
"""Diagnostik: DHCP-pool, statiska mappningar och ARP på EdgeRouter.

Skriver läsbar rapport till stdout och /config/www/edgerouter-dhcp-inspect.txt
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OUTPUT_PATH = Path("/config/www/edgerouter-dhcp-inspect.txt")

ENDPOINTS = (
    "dhcp-server-leases",
    "dhcp_leases",
    "dhcp-server-static-mapping",
    "dhcp_static",
    "dhcp-server-config",
    "dhcp-server-settings",
    "arp",
    "dhcp-server-lease-stats",
)


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


def login(host: str, username: str, password: str):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    cookie_jar = http.cookiejar.CookieJar()
    login_data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode()
    last_error: Exception | None = None
    for scheme in ("https", "http"):
        try:
            handlers = [urllib.request.HTTPCookieProcessor(cookie_jar)]
            if scheme == "https":
                handlers.append(urllib.request.HTTPSHandler(context=ctx))
            opener = urllib.request.build_opener(*handlers)
            login_req = urllib.request.Request(
                f"{scheme}://{host}/",
                data=login_data,
                method="POST",
            )
            opener.open(login_req, timeout=10)
            return opener, scheme, host
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("login failed")


def fetch_json(opener, scheme: str, host: str, endpoint: str):
    for path in (
        f"/api/edge/data.json?data={endpoint}",
        f"/api/edge/legacy/data.json?data={endpoint}",
    ):
        try:
            req = urllib.request.Request(f"{scheme}://{host}{path}")
            with opener.open(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            continue
    return None


def walk_strings(value, hits: list[str], needle: str) -> None:
    needle_l = needle.lower()
    if isinstance(value, dict):
        for key, item in value.items():
            text = f"{key} {item}"
            if needle_l in text.lower():
                hits.append(json.dumps({key: item}, ensure_ascii=False)[:500])
            walk_strings(item, hits, needle)
    elif isinstance(value, list):
        for item in value:
            walk_strings(item, hits, needle)
    elif isinstance(value, str) and needle_l in value.lower():
        hits.append(value)


def main() -> None:
    secrets = load_secrets()
    host = secrets.get("edgerouter_host", "192.168.0.1")
    username = secrets.get("edgerouter_username", "")
    password = secrets.get("edgerouter_password", "")
    if len(sys.argv) >= 4:
        host, username, password = sys.argv[1], sys.argv[2], sys.argv[3]

    opener, scheme, host = login(host, username, password)
    lines = [f"host={host} user={username} scheme={scheme}", ""]
    needles = ("192.168.0.9", "galaxy-s23", "galaxy", "erik", "1a:09:41", "1a09413c664f")

    for endpoint in ENDPOINTS:
        payload = fetch_json(opener, scheme, host, endpoint)
        lines.append(f"=== {endpoint} ===")
        if payload is None:
            lines.append("(saknas eller fel)")
            lines.append("")
            continue
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        lines.append(text[:12000])
        if len(text) > 12000:
            lines.append("... [trunkerad] ...")
        lines.append("")
        for needle in needles:
            hits: list[str] = []
            walk_strings(payload, hits, needle)
            if hits:
                lines.append(f"-- träffar för '{needle}' i {endpoint} --")
                for hit in hits[:20]:
                    lines.append(hit)
                lines.append("")

    report = "\n".join(lines)
    OUTPUT_PATH.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
