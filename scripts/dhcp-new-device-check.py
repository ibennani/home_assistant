#!/usr/bin/env python3
"""Jämför DHCP-klienter mot kända MAC och flaggar helt nya enheter.

Läser senaste poll från /config/www/edgerouter-dhcp-last.json.
Sparar kända MAC i /config/known_dhcp_macs.json (skapas på HA-servern).
Skriver väntande notiser till /config/www/dhcp-new-devices-pending.json.

Första körningen: registrerar alla nuvarande enheter (utom undantag) utan notis.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

INFRA_MACS = {
    "f0:9f:c2:64:3d:cc",
    "02:42:c0:a8:00:0a",
    "02:42:c0:a8:00:0b",
    "3c:e1:a1:b4:29:f4",
}
LAST_PATH = Path("/config/www/edgerouter-dhcp-last.json")
KNOWN_PATH = Path("/config/known_dhcp_macs.json")
PENDING_PATH = Path("/config/www/dhcp-new-devices-pending.json")
EXCLUSIONS_PATH = Path("/config/includes/wifi_client_exclusions.yaml")
NAMES_PATH = Path("/config/includes/wifi_client_names.yaml")


def normalize_mac(mac: str) -> str:
    return mac.strip().lower()


def load_mac_list_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    macs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r'^-\s*"([^"]+)"', line.strip())
        if match:
            macs.add(normalize_mac(match.group(1)))
    return macs


def load_name_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    names: dict[str, str] = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "names:":
            in_names = True
            continue
        if not in_names or not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([0-9a-fA-F]+)\s*:\s*(.+)$", stripped)
        if match:
            names[match.group(1).lower()] = match.group(2).strip()
    return names


def load_known() -> set[str]:
    if not KNOWN_PATH.exists():
        return set()
    try:
        payload = json.loads(KNOWN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {normalize_mac(mac) for mac in payload.get("macs", [])}


def save_known(macs: set[str]) -> None:
    KNOWN_PATH.write_text(
        json.dumps({"macs": sorted(macs)}, indent=2) + "\n",
        encoding="utf-8",
    )


def write_pending(devices: list[dict]) -> None:
    payload = {"count": len(devices), "devices": devices}
    PENDING_PATH.write_text(json.dumps(payload), encoding="utf-8")


def label_for(client: dict, names: dict[str, str]) -> str:
    key = normalize_mac(client.get("mac", "")).replace(":", "")
    return names.get(key) or client.get("hostname") or client.get("mac") or "Okänd enhet"


def main() -> None:
    skip = INFRA_MACS | load_mac_list_yaml(EXCLUSIONS_PATH)
    names = load_name_map(NAMES_PATH)

    if not LAST_PATH.exists():
        write_pending([])
        return

    try:
        payload = json.loads(LAST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        write_pending([])
        return

    clients = payload.get("data", [])
    tracked = [
        client
        for client in clients
        if isinstance(client, dict) and normalize_mac(client.get("mac", "")) not in skip
    ]
    current_macs = {normalize_mac(client["mac"]) for client in tracked if client.get("mac")}

    known = load_known()
    first_run = not KNOWN_PATH.exists()

    if first_run:
        save_known(current_macs)
        write_pending([])
        return

    new_macs = current_macs - known
    new_devices = []
    for client in tracked:
        mac = normalize_mac(client.get("mac", ""))
        if mac in new_macs:
            new_devices.append(
                {
                    "mac": mac,
                    "ip": client.get("ip", ""),
                    "hostname": client.get("hostname", ""),
                    "label": label_for(client, names),
                }
            )

    save_known(known | current_macs)
    write_pending(new_devices)


if __name__ == "__main__":
    main()
