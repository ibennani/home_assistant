#!/usr/bin/env python3
"""Jämför DHCP-klienter mot kända MAC och notifierar helt nya enheter.

Läser senaste poll från /config/www/edgerouter-dhcp-last.json.
Sparar kända MAC i /config/known_dhcp_macs.json (skapas på HA-servern).

Första körningen: registrerar alla nuvarande enheter (utom undantag) utan notis.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

INFRA_MACS = {
    "f0:9f:c2:64:3d:cc",
    "02:42:c0:a8:00:0a",
    "02:42:c0:a8:00:0b",
    "3c:e1:a1:b4:29:f4",
}
LAST_PATH = Path("/config/www/edgerouter-dhcp-last.json")
KNOWN_PATH = Path("/config/known_dhcp_macs.json")
DEBUG_PATH = Path("/config/www/dhcp-new-device-debug.txt")
EXCLUSIONS_PATH = Path("/config/includes/wifi_client_exclusions.yaml")
NAMES_PATH = Path("/config/includes/wifi_client_names.yaml")
SECRETS_PATH = Path("/config/secrets.yaml")
NOTIFY_TARGET = "mobile_app_ilias_s23_ultra"


def normalize_mac(mac: str) -> str:
    return mac.strip().lower()


def load_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in SECRETS_PATH.read_text(encoding="utf-8").splitlines():
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


def label_for(client: dict, names: dict[str, str]) -> str:
    key = normalize_mac(client.get("mac", "")).replace(":", "")
    return names.get(key) or client.get("hostname") or client.get("mac") or "Okänd enhet"


def send_mobilnotis(meddelande: str, secrets: dict[str, str]) -> bool:
    url = secrets.get("ha_internal_url", "http://127.0.0.1:8123").rstrip("/")
    token = secrets.get("ha_long_lived_token", "")
    if not token:
        return False
    payload = json.dumps(
        {
            "entity_id": "script.mobilnotis",
            "variables": {
                "mottagare": NOTIFY_TARGET,
                "meddelande": meddelande,
                "prefix_hemmet": True,
            },
        }
    ).encode()
    request = urllib.request.Request(
        f"{url}/api/services/script/turn_on",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8):
            return True
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def main() -> None:
    secrets = load_secrets()
    skip = INFRA_MACS | load_mac_list_yaml(EXCLUSIONS_PATH)
    names = load_name_map(NAMES_PATH)

    if not LAST_PATH.exists():
        DEBUG_PATH.write_text("missing edgerouter-dhcp-last.json\n", encoding="utf-8")
        return

    try:
        payload = json.loads(LAST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        DEBUG_PATH.write_text("invalid edgerouter-dhcp-last.json\n", encoding="utf-8")
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
        DEBUG_PATH.write_text(
            f"init known={len(current_macs)} macs\n",
            encoding="utf-8",
        )
        return

    new_macs = current_macs - known
    notified = 0
    for client in tracked:
        mac = normalize_mac(client.get("mac", ""))
        if mac not in new_macs:
            continue
        label = label_for(client, names)
        ip = client.get("ip", "")
        meddelande = f"Ny enhet på nätet: {label} — {ip} ({mac})"
        if send_mobilnotis(meddelande, secrets):
            notified += 1

    save_known(known | current_macs)
    DEBUG_PATH.write_text(
        f"new={len(new_macs)} notified={notified} token={'yes' if secrets.get('ha_long_lived_token') else 'no'}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
