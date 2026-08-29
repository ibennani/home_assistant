#!/usr/bin/env python3
"""Synka zonlistor på map-kort i Översikt-dashboarden (utom Blixtkartan).

Hämtar alla zone.*-entiteter från Home Assistant och uppdaterar markerade
block i dashboards/dashboard-september-2025.yaml. Kort utan map-zones-markör
(t.ex. Blixtkartan) påverkas inte.

Kör: python3 scripts/sync-dashboard-map-zones.py --patch
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_FILE = ROOT / "dashboards" / "dashboard-september-2025.yaml"
MAP_ZONES_BEGIN = "# BEGIN map-zones (scripts/sync-dashboard-map-zones.py)"
MAP_ZONES_END = "# END map-zones"

# UI-dubbletter som inte ska med på kartorna
EXCLUDE_ZONES = frozenset({"zone.justus_2", "zone.rodkinda_19_2"})


def load_ha_env() -> tuple[str, str]:
    ha_url = os.environ.get("HA_URL", "").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN", "")
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("HA_URL=") and not ha_url:
                ha_url = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            elif line.startswith("HA_TOKEN=") and not ha_token:
                ha_token = line.split("=", 1)[1].strip().strip('"')
    if not ha_url or not ha_token:
        raise SystemExit("HA_URL/HA_TOKEN saknas (.env eller miljövariabler)")
    return ha_url, ha_token


def fetch_zone_entity_ids() -> list[str]:
    ha_url, ha_token = load_ha_env()
    req = urllib.request.Request(
        f"{ha_url}/api/states",
        headers={"Authorization": f"Bearer {ha_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            states = json.load(resp)
    except urllib.error.URLError as exc:
        raise SystemExit(f"Kunde inte hämta states från HA: {exc}") from exc

    zones = sorted(
        state["entity_id"]
        for state in states
        if state.get("entity_id", "").startswith("zone.")
        and state["entity_id"] not in EXCLUDE_ZONES
    )
    if not zones:
        raise SystemExit("Inga zoner hittades i HA")
    return zones


def build_zone_block(zones: list[str]) -> str:
    lines = [MAP_ZONES_BEGIN]
    lines.extend(f"      - {zone}" for zone in zones)
    lines.append(f"      {MAP_ZONES_END}")
    return "\n".join(lines)


def replace_map_zone_blocks(content: str, zone_block: str) -> str:
    pattern = re.compile(
        re.escape(MAP_ZONES_BEGIN) + r".*?" + re.escape(MAP_ZONES_END),
        re.DOTALL,
    )
    matches = pattern.findall(content)
    if not matches:
        raise SystemExit(
            f"Inga {MAP_ZONES_BEGIN!r}-block hittades i {DASHBOARD_FILE}. "
            "Lägg till marker i map-korten först."
        )
    return pattern.sub(zone_block, content)


def patch_dashboard(zones: list[str] | None = None) -> list[str]:
    zones = zones if zones is not None else fetch_zone_entity_ids()
    content = DASHBOARD_FILE.read_text(encoding="utf-8")
    zone_block = build_zone_block(zones)
    updated = replace_map_zone_blocks(content, zone_block)
    if updated == content:
        print("Inga ändringar behövdes", file=sys.stderr)
        return zones
    DASHBOARD_FILE.write_text(updated, encoding="utf-8")
    count = updated.count(MAP_ZONES_BEGIN)
    print(f"Uppdaterade {count} map-zonblock med {len(zones)} zoner", file=sys.stderr)
    return zones


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--patch",
        action="store_true",
        help="Skriv zonlistan till dashboard YAML",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Skriv zonlistan till stdout (en per rad)",
    )
    args = parser.parse_args()

    zones = fetch_zone_entity_ids()

    if args.list:
        for zone in zones:
            print(zone)
        return

    if args.patch:
        patch_dashboard(zones)
        return

    parser.print_help()
    raise SystemExit(2)


if __name__ == "__main__":
    main()
