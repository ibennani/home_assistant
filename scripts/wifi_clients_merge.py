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
    """UniFi wireless först; DHCP bara för aktiva UniFi-MAC eller när UniFi saknas."""
    merged: list[dict] = []
    seen_macs: set[str] = set()
    seen_ips: set[str] = set()

    unifi_active_macs = {
        normalize_mac(str(client.get("mac") or ""))
        for client in unifi_clients
        if isinstance(client, dict) and client.get("mac")
    }
    unifi_ok = len(unifi_clients) > 0

    for client in unifi_clients:
        if not isinstance(client, dict):
            continue
        if client.get("is_wired"):
            continue
        mac = normalize_mac(str(client.get("mac") or ""))
        if not mac or mac in skip:
            continue
        ip = str(client.get("ip") or "").strip()
        if not ip:
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
        seen_ips.add(ip)

    for client in dhcp_clients:
        if not isinstance(client, dict):
            continue
        mac = normalize_mac(str(client.get("mac") or ""))
        if not mac or mac in skip:
            continue
        if unifi_ok and mac not in unifi_active_macs:
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
            }
        )
        seen_macs.add(mac)
        if ip:
            seen_ips.add(ip)

    merged.sort(key=lambda item: (item.get("hostname") or item["mac"]).lower())
    return merged


def load_merged(skip: set[str]) -> list[dict]:
    return merge_wifi_clients(load_json_list(DHCP_LAST_PATH), load_json_list(UNIFI_LAST_PATH), skip)


def _self_test() -> None:
    skip: set[str] = set()
    unifi = [
        {
            "mac": "aa:bb:cc:dd:ee:01",
            "ip": "192.168.0.50",
            "hostname": "annas-mobil",
            "essid": "Hemma",
            "is_wired": False,
            "is_guest": False,
        },
        {
            "mac": "aa:bb:cc:dd:ee:02",
            "ip": "192.168.0.51",
            "hostname": "printer",
            "essid": "",
            "is_wired": True,
            "is_guest": False,
        },
    ]
    dhcp = [
        {"mac": "72:41:2e:7e:c9:0a", "ip": "192.168.0.50", "hostname": "stale-ilias"},
        {"mac": "aa:bb:cc:dd:ee:02", "ip": "192.168.0.51", "hostname": "printer"},
    ]
    merged = merge_wifi_clients(dhcp, unifi, skip)
    macs = {item["mac"] for item in merged}
    assert "aa:bb:cc:dd:ee:01" in macs
    assert "72:41:2e:7e:c9:0a" not in macs
    assert "aa:bb:cc:dd:ee:02" in macs

    fallback = merge_wifi_clients(dhcp, [], skip)
    assert len(fallback) == 2


def main() -> None:
    import sys

    if "--test" in sys.argv:
        _self_test()
        print("wifi_clients_merge: OK")
        return
    print(json.dumps({"count": 0, "data": []}))


if __name__ == "__main__":
    main()
