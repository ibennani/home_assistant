#!/usr/bin/env python3
"""Hämtar aktiva DHCP-leases från EdgeRouter.

Läser edgerouter_host, edgerouter_username och edgerouter_password
från /config/secrets.yaml. Utan giltiga uppgifter returneras tom lista.

Användning:
  python3 edgerouter-dhcp-clients.py              # skriv JSON till stdout
  python3 edgerouter-dhcp-clients.py /path/out.json
"""
from __future__ import annotations

import http.cookiejar
import importlib.util
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

socket.setdefaulttimeout(8)

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


def empty_result() -> dict:
    return {"count": 0, "data": []}


def login_and_fetch(host: str, username: str, password: str) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    cookie_jar = http.cookiejar.CookieJar()
    login_data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode()

    last_error: Exception | None = None
    endpoints = (
        "dhcp_leases",
        "dhcp-server-leases",
        "dhcp_dynamic",
        "arp",
    )
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
            opener.open(login_req, timeout=8)

            for endpoint in endpoints:
                for path in (
                    f"/api/edge/data.json?data={endpoint}",
                    f"/api/edge/legacy/data.json?data={endpoint}",
                ):
                    leases_req = urllib.request.Request(f"{scheme}://{host}{path}")
                    try:
                        with opener.open(leases_req, timeout=8) as response:
                            payload = json.loads(response.read().decode("utf-8"))
                    except (urllib.error.HTTPError, json.JSONDecodeError):
                        continue
                    unwrapped = unwrap_payload(payload)
                    if any(
                        unwrapped.get(k)
                        for k in ("dhcp_leases", "dhcp-server-leases", "lease", "arp")
                    ):
                        return payload
            raise RuntimeError("no dhcp data in EdgeRouter response")
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            TimeoutError,
            OSError,
            ValueError,
        ) as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise RuntimeError("EdgeRouter login failed")


def unwrap_payload(payload: dict) -> dict:
    if "dhcp_leases" in payload:
        return payload
    output = payload.get("output")
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return payload
    if isinstance(output, dict):
        return output
    return payload


def lease_expires_ts(lease: dict) -> int:
    for key in ("expires", "lease-end", "end", "expiration"):
        raw = lease.get(key)
        if raw is None:
            continue
        if str(raw).isdigit():
            return int(raw)
    return 0


def lease_is_active(lease: dict, now: int | None = None) -> bool:
    now = now if now is not None else int(time.time())
    expires = lease_expires_ts(lease)
    if expires and expires < now:
        return False
    active = str(lease.get("active", "1")).lower()
    if active in ("0", "false", "no", "off"):
        return False
    return True


def parse_dhcp_server_leases(block: dict) -> list[dict]:
    """EdgeOS: dhcp-server-leases → interface → IP-keyed lease dict."""
    clients: list[dict] = []
    now = int(time.time())
    for iface_data in block.values():
        if not isinstance(iface_data, dict):
            continue
        for ip, lease in iface_data.items():
            if not isinstance(lease, dict):
                continue
            if not lease_is_active(lease, now):
                continue
            mac = normalize_mac(
                str(
                    lease.get("mac")
                    or lease.get("mac-address")
                    or lease.get("hwaddr")
                    or ""
                )
            )
            if not mac or mac in INFRA_MACS:
                continue
            hostname = str(
                lease.get("client-hostname")
                or lease.get("hostname")
                or lease.get("host-name")
                or lease.get("name")
                or ""
            ).strip()
            clients.append(
                {
                    "mac": mac,
                    "ip": str(ip).strip(),
                    "hostname": hostname,
                    "expires": lease_expires_ts(lease),
                }
            )
    return clients


def parse_flat_leases(leases: list | dict) -> list[dict]:
    if isinstance(leases, dict):
        leases = [leases]

    clients: list[dict] = []
    now = int(time.time())

    for lease in leases:
        if not isinstance(lease, dict):
            continue
        if not lease_is_active(lease, now):
            continue
        mac = normalize_mac(
            str(lease.get("mac") or lease.get("mac-address") or lease.get("hwaddr") or "")
        )
        if not mac or mac in INFRA_MACS:
            continue
        expires = lease_expires_ts(lease)
        hostname = str(
            lease.get("hostname")
            or lease.get("host-name")
            or lease.get("client-hostname")
            or lease.get("name")
            or ""
        ).strip()
        ip = str(
            lease.get("ip")
            or lease.get("ip-address")
            or lease.get("address")
            or ""
        ).strip()
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
    return clients


def parse_leases(payload: dict) -> list[dict]:
    payload = unwrap_payload(payload)

    dhcp_server = payload.get("dhcp-server-leases")
    if isinstance(dhcp_server, dict) and dhcp_server:
        clients = parse_dhcp_server_leases(dhcp_server)
        if clients:
            clients.sort(key=lambda item: (item.get("hostname") or item["ip"]).lower())
            return clients

    leases: list | dict = []
    for key in ("dhcp_leases", "arp"):
        block = payload.get(key)
        if not block:
            continue
        if isinstance(block, dict):
            if "lease" in block:
                leases = block.get("lease", [])
            elif "leases" in block:
                leases = block.get("leases", [])
            elif "entry" in block:
                leases = block.get("entry", [])
            else:
                leases = list(block.values())
        elif isinstance(block, list):
            leases = block
        if leases:
            break

    clients = parse_flat_leases(leases)
    clients.sort(key=lambda item: (item.get("hostname") or item["ip"]).lower())
    return clients


def credential_pairs(secrets: dict[str, str]) -> list[tuple[str, str, str]]:
    host = secrets.get("edgerouter_host", "192.168.0.1")
    pairs: list[tuple[str, str, str]] = []
    username = secrets.get("edgerouter_username", "")
    password = secrets.get("edgerouter_password", "")
    if username not in PLACEHOLDER_VALUES and password not in PLACEHOLDER_VALUES:
        pairs.append((host, username, password))
    pairs.append((host, "ubnt", "ubnt"))
    return pairs


def fetch_clients(secrets: dict[str, str]) -> tuple[list[dict], str, str]:
    last_error: Exception | None = None
    for host, username, password in credential_pairs(secrets):
        try:
            payload = login_and_fetch(host, username, password)
            clients = parse_leases(payload)
            if clients:
                return clients, host, username
            last_error = RuntimeError("login ok but no dhcp leases parsed")
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return [], secrets.get("edgerouter_host", "192.168.0.1"), secrets.get("edgerouter_username", "")


LAST_DHCP_PATH = Path("/config/www/edgerouter-dhcp-last.json")


def emit(result: dict, output_path: str | None) -> None:
    payload = json.dumps(result)
    LAST_DHCP_PATH.write_text(payload, encoding="utf-8")
    if output_path:
        Path(output_path).write_text(payload, encoding="utf-8")
    else:
        print(payload)


def run_new_device_check() -> None:
    path = Path("/config/scripts/dhcp-new-device-check.py")
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location("dhcp_new_device_check", path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run_check()


def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else None
    debug_path = Path("/config/www/edgerouter-debug.txt")
    try:
        secrets = load_secrets()
        clients, host, username = fetch_clients(secrets)
        result = {"count": len(clients), "data": clients}
        debug_path.write_text(
            f"ok host={host} user={username} leases={len(clients)} preview={json.dumps(result)[:300]}\n",
            encoding="utf-8",
        )
        emit(result, output_path)
        run_new_device_check()
    except Exception as exc:
        debug_path.write_text(f"error: {exc!r}\n", encoding="utf-8")
        emit(empty_result(), output_path)


if __name__ == "__main__":
    main()
