#!/usr/bin/env python3
"""Beräkna tvättmaskinens kostnad vid klar utifrån effekthistorik och Nord Pool-kvartar.

Körs på HA-servern via EdgeRouter DHCP-sensor (update_entity) när tvättmaskinen blir klar (aktiv av).
Sätter input_text.tvattmaskin_senaste_kostnaden (t.ex. "1,68") eller tom sträng vid fel.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SECRETS_PATH = Path("/config/secrets.yaml")
POWER_ENTITY = "sensor.tvattmaskinen_switch_power"
NORDPOOL_ENTITY = "sensor.nordpool_kwh_se3_sek_3_10_025"
COST_ENTITY = "input_text.tvattmaskin_senaste_kostnaden"

LOOKBACK_HOURS = 12
LOW_W = 5.0
START_W = 50.0
IDLE_MINUTES = 5.0


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


def api_request(
    secrets: dict[str, str],
    method: str,
    path: str,
    body: dict | None = None,
) -> object:
    base = secrets.get("ha_internal_url", "http://127.0.0.1:8123").rstrip("/")
    token = secrets.get("ha_long_lived_token", "")
    if not token:
        raise RuntimeError("ha_long_lived_token saknas i secrets.yaml")
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fetch_power_history(secrets: dict[str, str], end: datetime) -> list[tuple[datetime, float]]:
    end_param = urllib.parse.quote(end.isoformat())
    path = (
        f"/api/history/period/{end_param}"
        f"?filter_entity_id={urllib.parse.quote(POWER_ENTITY)}"
        f"&minimal_response=true"
        f"&no_attributes=true"
    )
    raw = api_request(secrets, "GET", path)
    if not raw or not isinstance(raw, list) or not raw[0]:
        return []
    points: list[tuple[datetime, float]] = []
    for row in raw[0]:
        try:
            points.append((parse_iso(row["last_changed"]), float(row["state"])))
        except (KeyError, TypeError, ValueError):
            continue
    points.sort(key=lambda x: x[0])
    cutoff = end - timedelta(hours=LOOKBACK_HOURS)
    return [(t, v) for t, v in points if t >= cutoff]


def fetch_nordpool_slots(secrets: dict[str, str]) -> list[tuple[datetime, datetime, float]]:
    state = api_request(secrets, "GET", f"/api/states/{NORDPOOL_ENTITY}")
    attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
    slots_raw = list(attrs.get("raw_today") or [])
    tmr = attrs.get("tomorrow_valid")
    tm_ok = tmr is True or (isinstance(tmr, str) and tmr.lower() == "true")
    if tm_ok:
        slots_raw.extend(attrs.get("raw_tomorrow") or [])
    slots: list[tuple[datetime, datetime, float]] = []
    for s in slots_raw:
        try:
            slots.append(
                (
                    parse_iso(s["start"]),
                    parse_iso(s["end"]),
                    float(s["value"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return slots


def find_last_run_start(
    points: list[tuple[datetime, float]],
    end: datetime,
) -> datetime | None:
    """Senaste tvättstart: första >= START_W efter minst IDLE_MINUTES med <= LOW_W."""
    if not points:
        return None
    idle_min_s = IDLE_MINUTES * 60
    last_start: datetime | None = None
    last_low_at: datetime | None = None

    for t, v in points:
        if t > end:
            break
        if v <= LOW_W:
            last_low_at = t
        elif v >= START_W:
            if last_low_at is not None and (t - last_low_at).total_seconds() >= idle_min_s:
                last_start = t
            elif last_start is None and last_low_at is not None:
                # Kort vila före start (t.ex. 18:03 → 18:06) — räkna ändå som ny tvätt
                last_start = t

    return last_start


def find_last_run_end(
    points: list[tuple[datetime, float]],
    start: datetime,
    cap_end: datetime,
) -> datetime:
    """Senaste tidpunkt med märkbar effekt efter start (för sent manuellt test)."""
    last_active = start
    for t, v in points:
        if t < start or t > cap_end:
            continue
        if v > LOW_W:
            last_active = t
    return min(cap_end, last_active + timedelta(minutes=2))


def price_at(slots: list[tuple[datetime, datetime, float]], t: datetime) -> float | None:
    for s0, s1, price in slots:
        if s0 <= t < s1:
            return price
    return None


def integrate_cost(
    points: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
    slots: list[tuple[datetime, datetime, float]],
) -> tuple[float, float]:
    """Returnerar (kWh, kostnad_kr)."""
    series = [(t, v) for t, v in points if start <= t <= end]
    if not series:
        return 0.0, 0.0
    if series[0][0] > start:
        series.insert(0, (start, series[0][1]))
    if series[-1][0] < end:
        series.append((end, series[-1][1]))

    total_kwh = 0.0
    total_kr = 0.0
    for i in range(1, len(series)):
        t0, p0 = series[i - 1]
        t1, p1 = series[i]
        dt_s = (t1 - t0).total_seconds()
        if dt_s <= 0:
            continue
        t = t0
        while t < t1:
            next_t = t1
            for s0, s1, _ in slots:
                for boundary in (s0, s1):
                    if t < boundary < next_t:
                        next_t = boundary
            frac = (next_t - t).total_seconds() / dt_s
            p = p0 + (p1 - p0) * ((t - t0).total_seconds() / dt_s)
            e = p * (next_t - t).total_seconds() / 3600.0 / 1000.0
            total_kwh += e
            pr = price_at(slots, t)
            if pr is not None:
                total_kr += e * pr
            t = next_t
    return total_kwh, total_kr


def format_kr(kr: float) -> str:
    return f"{kr:.2f}".replace(".", ",")


def set_cost_text(secrets: dict[str, str], value: str) -> None:
    api_request(
        secrets,
        "POST",
        "/api/services/input_text/set_value",
        {"entity_id": COST_ENTITY, "value": value},
    )


def main() -> int:
    secrets = load_secrets()
    end = datetime.now().astimezone()
    try:
        points = fetch_power_history(secrets, end)
        slots = fetch_nordpool_slots(secrets)
        start = find_last_run_start(points, end)
        if start is None or not slots:
            set_cost_text(secrets, "")
            return 0
        run_end = find_last_run_end(points, start, end)
        kwh, kr = integrate_cost(points, start, run_end, slots)
        if kr < 0.001 or kwh < 0.001:
            set_cost_text(secrets, "")
            return 0
        set_cost_text(secrets, format_kr(kr))
        print(f"tvattmaskin kostnad: {kwh:.3f} kWh, {format_kr(kr)} kr")
        return 0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError) as exc:
        print(f"tvattmaskin kostnad: fel {exc}", file=sys.stderr)
        try:
            set_cost_text(secrets, "")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError):
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
