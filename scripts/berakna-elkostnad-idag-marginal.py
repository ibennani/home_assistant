#!/usr/bin/env python3
"""Beräkna dagens elkostnad (kr) utifrån Tibber ackumulerad kWh och marginalpris per kvart."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SECRETS_PATH = Path("/config/secrets.yaml")
CONSUMPTION_ENTITY = "sensor.accumulated_consumption_eksharadsgatan_6"
ELPRIS_ENTITY = "sensor.elpris_marginal_kwh_se3"
TZ = ZoneInfo("Europe/Stockholm")


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


def ha_auth(secrets: dict[str, str]) -> tuple[str, str]:
    token = (
        secrets.get("ha_long_lived_token", "").strip()
        or os.environ.get("HA_TOKEN", "").strip()
        or os.environ.get("SUPERVISOR_TOKEN", "").strip()
    )
    base = secrets.get("ha_internal_url", "http://127.0.0.1:8123").rstrip("/")
    if token and os.environ.get("SUPERVISOR_TOKEN"):
        base = "http://supervisor/core"
    return base, token


def api_get(secrets: dict[str, str], path: str) -> object:
    base, token = ha_auth(secrets)
    if not token:
        raise RuntimeError("saknar HA-token")
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def coerce_slot_list(raw: object) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def parse_slot_row(s: object) -> tuple[datetime, datetime, float] | None:
    if not isinstance(s, dict):
        return None
    start_raw = s.get("start")
    end_raw = s.get("end")
    val = s.get("value")
    if start_raw is None or end_raw is None:
        return None
    try:
        start = parse_iso(str(start_raw))
        end = parse_iso(str(end_raw))
        price = float(val)
    except (TypeError, ValueError):
        return None
    return start, end, price


def fetch_marginal_slots(secrets: dict[str, str]) -> list[tuple[datetime, datetime, float]]:
    states = api_get(secrets, f"/api/states/{ELPRIS_ENTITY}")
    if not isinstance(states, dict):
        return []
    attrs = states.get("attributes") or {}
    slots: list[tuple[datetime, datetime, float]] = []
    for key in ("raw_today",):
        for s in coerce_slot_list(attrs.get(key)):
            row = parse_slot_row(s)
            if row:
                slots.append(row)
    if slots:
        return sorted(slots, key=lambda x: x[0])
    today = coerce_slot_list(attrs.get("today"))
    if not today:
        return []
    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    step = 15 if len(today) > 24 else 60
    for i, val in enumerate(today):
        start = midnight + timedelta(minutes=i * step)
        end = start + timedelta(minutes=step)
        try:
            slots.append((start, end, float(val)))
        except (TypeError, ValueError):
            continue
    return slots


def fetch_consumption_history(
    secrets: dict[str, str], start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    start_utc = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    path = (
        f"/api/history/period/{urllib.parse.quote(start_utc, safe='')}"
        f"?filter_entity_id={CONSUMPTION_ENTITY}&minimal_response&no_attributes"
    )
    data = api_get(secrets, path)
    points: list[tuple[datetime, float]] = []
    if not isinstance(data, list) or not data:
        return points
    entity_rows = data[0] if isinstance(data[0], list) else []
    for row in entity_rows:
        if not isinstance(row, dict):
            continue
        try:
            t = parse_iso(str(row.get("last_changed") or row.get("last_updated")))
            v = float(row.get("state"))
        except (TypeError, ValueError):
            continue
        if v < 0:
            continue
        points.append((t, v))
    points.sort(key=lambda x: x[0])
    return points


def value_at(points: list[tuple[datetime, float]], t: datetime) -> float:
    if not points:
        return 0.0
    last = 0.0
    for pt, val in points:
        if pt <= t:
            last = val
        else:
            break
    return last


def compute_cost(
    slots: list[tuple[datetime, datetime, float]],
    points: list[tuple[datetime, float]],
    now: datetime,
) -> float:
    total = 0.0
    for start, end, price in slots:
        if start >= now:
            break
        slot_end = min(end, now)
        if slot_end <= start:
            continue
        kwh_start = value_at(points, start)
        kwh_end = value_at(points, slot_end)
        delta = max(0.0, kwh_end - kwh_start)
        total += delta * price
    return total


def fallback_estimate(secrets: dict[str, str]) -> float:
    states = api_get(secrets, f"/api/states/{CONSUMPTION_ENTITY}")
    elpris = api_get(secrets, f"/api/states/{ELPRIS_ENTITY}")
    if not isinstance(states, dict) or not isinstance(elpris, dict):
        return 0.0
    try:
        kwh = float(states.get("state") or 0)
    except (TypeError, ValueError):
        kwh = 0.0
    attrs = elpris.get("attributes") or {}
    today = coerce_slot_list(attrs.get("today"))
    if not today:
        try:
            avg = float(elpris.get("state") or 0)
        except (TypeError, ValueError):
            avg = 0.0
    else:
        avg = sum(float(x) for x in today) / len(today)
    return round(kwh * avg, 2)


def main() -> int:
    secrets = load_secrets()
    now = datetime.now(TZ)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        slots = fetch_marginal_slots(secrets)
        points = fetch_consumption_history(secrets, midnight - timedelta(minutes=5), now)
        if not slots or not points:
            print(f"{fallback_estimate(secrets):.2f}")
            return 0
        cost = compute_cost(slots, points, now)
        if cost <= 0:
            cost = fallback_estimate(secrets)
        print(f"{cost:.2f}")
        return 0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        try:
            print(f"{fallback_estimate(secrets):.2f}")
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
            print("0.00")
            return 1


if __name__ == "__main__":
    sys.exit(main())
