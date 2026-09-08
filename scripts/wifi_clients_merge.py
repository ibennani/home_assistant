#!/usr/bin/env python3
"""Slår ihop EdgeRouter DHCP och UniFi WLAN till en klientlista för Wi-Fi-vyn."""
from __future__ import annotations

import json
from pathlib import Path

DHCP_LAST_PATH = Path("/config/www/edgerouter-dhcp-last.json")
UNIFI_LAST_PATH = Path("/config/www/unifi-wlan-last.json")


def normalize_mac(mac: str) -> str:
    return mac.strip().lower()


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    data = payload.get("data", [])
    return data if isinstance(data, list) else []


def merge_wifi_clients(
    dhcp_clients: list[dict],
    unifi_clients: list[dict],
    skip: set[str],
) -> list[dict]:
    merged: list[dict] = []
    seen_macs: set[str] = set()
    seen_ips: set[str] = set()

    for client in dhcp_clients:
        if not isinstance(client, dict):
            continue
        mac = normalize_mac(str(client.get("mac") or ""))
        if not mac or mac in skip:
            continue
        ip = str(client.get("ip") or "").strip()
        merged.append(
            {
                "mac": mac,
                "ip": ip,
                "hostname": str(client.get("hostname") or "").strip(),
            }
        )
        seen_macs.add(mac)
        if ip:
            seen_ips.add(ip)

    for client in unifi_clients:
        if not isinstance(client, dict):
            continue
        if client.get("is_wired"):
            continue
        mac = normalize_mac(str(client.get("mac") or ""))
        if not mac or mac in skip:
            continue
        ip = str(client.get("ip") or "").strip()
        if mac in seen_macs:
            continue
        if ip and ip in seen_ips:
            continue
        merged.append(
            {
                "mac": mac,
                "ip": ip,
                "hostname": str(client.get("hostname") or "").strip(),
                "essid": str(client.get("essid") or "").strip(),
                "is_guest": bool(client.get("is_guest")),
            }
        )
        seen_macs.add(mac)
        if ip:
            seen_ips.add(ip)

    merged.sort(key=lambda item: (item.get("hostname") or item["mac"]).lower())
    return merged


def load_merged(skip: set[str]) -> list[dict]:
    return merge_wifi_clients(load_json_list(DHCP_LAST_PATH), load_json_list(UNIFI_LAST_PATH), skip)


def main() -> None:
    print(json.dumps({"count": 0, "data": []}))


if __name__ == "__main__":
    main()
