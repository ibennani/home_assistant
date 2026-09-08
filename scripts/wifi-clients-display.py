#!/usr/bin/env python3
"""Bygger markdown för Wi-Fi-fliken från DHCP + UniFi JSON-filer."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wifi_clients_merge import load_json_list, merge_wifi_clients

DHCP_LAST_PATH = Path("/config/www/edgerouter-dhcp-last.json")
UNIFI_LAST_PATH = Path("/config/www/unifi-wlan-last.json")
EXCLUSIONS_PATH = Path("/config/includes/wifi_client_exclusions.yaml")
NAMES_PATH = Path("/config/includes/wifi_client_names.yaml")

INFRA_MACS = {
    "f0:9f:c2:64:3d:cc",
    "02:42:c0:a8:00:0a",
    "02:42:c0:a8:00:0b",
    "3c:e1:a1:b4:29:f4",
    "60:6d:c7:5b:9e:85",
}


def load_mac_list_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    macs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r'^-\s*"([^"]+)"', line.strip())
        if match:
            macs.add(match.group(1).strip().lower())
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


def label_for(client: dict, names: dict[str, str]) -> str:
    key = str(client.get("mac", "")).replace(":", "").lower()
    return names.get(key) or client.get("hostname") or client.get("mac") or "Okänd enhet"


def network_label(client: dict) -> str:
    essid = str(client.get("essid") or "").strip()
    if essid:
        return essid
    if client.get("is_guest"):
        return "gäst"
    return "Wi-Fi"


def build_markdown(clients: list[dict], names: dict[str, str]) -> str:
    count = len(clients)
    word = "enhet" if count == 1 else "enheter"
    lines = [f"## {count}", "", f"{word} anslutna på nätet", ""]
    for index, client in enumerate(clients, start=1):
        label = label_for(client, names)
        net = network_label(client)
        ip = str(client.get("ip") or "—").strip() or "—"
        lines.append(f"**{index}.** {label} — {net} — {ip}")
    if not clients:
        lines.append("*Inga Wi-Fi-klienter just nu.*")
    return "\n".join(lines)


def main() -> None:
    skip = INFRA_MACS | load_mac_list_yaml(EXCLUSIONS_PATH)
    names = load_name_map(NAMES_PATH)
    clients = merge_wifi_clients(
        load_json_list(DHCP_LAST_PATH),
        load_json_list(UNIFI_LAST_PATH),
        skip,
    )
    # UniFi-only utan IP är oftast infrastruktur/spök — visa inte i listan.
    clients = [client for client in clients if str(client.get("ip") or "").strip()]
    markdown = build_markdown(clients, names)
    print(json.dumps({"count": len(clients), "markdown": markdown}))


if __name__ == "__main__":
    main()
