#!/usr/bin/env python3
"""Skapa eller uppdatera zoner i HA storage (redigerbara i frontend).

Används efter att YAML-zoner tagits bort från configuration.yaml.
Kräver HA_URL och HA_TOKEN (.env eller miljövariabler).

Kör: python3 scripts/seed-storage-zones.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Zondefinitioner som tidigare låg i includes/zone.yaml.
# Används av scripts/seed-storage-zones.py vid migration till storage.
ZONES = [
    {
        "name": "Home",
        "latitude": 59.237731498047985,
        "longitude": 18.087033927440647,
        "radius": 80,
        "icon": "mdi:home",
    },
    {
        "name": "Sahlgrenska sjukhuset",
        "latitude": 57.6822800214212,
        "longitude": 11.959862876683475,
        "radius": 461,
        "icon": "mdi:hospital-box-outline",
    },
    {
        "name": "Mölndahls sjukhus",
        "latitude": 57.66094070711746,
        "longitude": 12.010909840464592,
        "radius": 234,
        "icon": "mdi:hospital-box-outline",
    },
    {
        "name": "Justus",
        "latitude": 59.23149,
        "longitude": 18.073242,
        "radius": 20,
        "icon": "mdi:human",
    },
    {
        "name": "Rödkinda 19",
        "latitude": 59.235683,
        "longitude": 18.087751,
        "radius": 15,
        "icon": "mdi:human",
    },
    {
        "name": "Eddie",
        "latitude": 57.761141,
        "longitude": 12.041550,
        "radius": 20,
        "icon": "mdi:human",
    },
    {
        "name": "Isabelles hem",
        "latitude": 60.797749,
        "longitude": 10.692576,
        "radius": 420,
        "icon": "mdi:home",
    },
    {
        "name": "Albins jobb",
        "previous_names": ["Albins mamma"],
        "latitude": 59.3606569,
        "longitude": 17.9743128,
        "radius": 100,
        "icon": "mdi:briefcase",
    },
]


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


def ha_request(
    ha_url: str,
    ha_token: str,
    method: str,
    path: str,
    payload: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{ha_url}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else {}


def list_zones(ha_url: str, ha_token: str) -> list[dict]:
    return ha_request(ha_url, ha_token, "GET", "/api/config/zone_registry/list")


def upsert_zone(ha_url: str, ha_token: str, zone: dict, existing_by_name: dict[str, dict]) -> str:
    name = zone["name"]
    if name in existing_by_name:
        zone_id = existing_by_name[name]["id"]
        ha_request(
            ha_url,
            ha_token,
            "POST",
            "/api/config/zone_registry/update",
            {"id": zone_id, **zone},
        )
        return f"uppdaterad: {name} ({zone_id})"

    # Flyttad/omdöpt zon (t.ex. Albins mamma → Albins jobb)
    for previous_name in zone.get("previous_names", []):
        if previous_name in existing_by_name:
            zone_id = existing_by_name[previous_name]["id"]
            payload = {k: v for k, v in zone.items() if k != "previous_names"}
            ha_request(
                ha_url,
                ha_token,
                "POST",
                "/api/config/zone_registry/update",
                {"id": zone_id, **payload},
            )
            return f"omdöpt/uppdaterad: {previous_name} → {name} ({zone_id})"

    created = ha_request(
        ha_url,
        ha_token,
        "POST",
        "/api/config/zone_registry/create",
        zone,
    )
    zone_id = created.get("id", "?")
    return f"skapad: {name} ({zone_id})"


def main() -> int:
    ha_url, ha_token = load_ha_env()
    existing = list_zones(ha_url, ha_token)
    by_name = {z["name"]: z for z in existing}

    for zone in ZONES:
        try:
            result = upsert_zone(ha_url, ha_token, zone, by_name)
            print(result)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            print(f"FEL för {zone['name']}: {exc.code} {detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
