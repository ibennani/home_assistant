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
LOG_PATH = Path("/config/www/tvattmaskin-kostnad-last.log")
POWER_ENTITY = "sensor.tvattmaskinen_switch_power"
ACTIVE_ENTITY = "binary_sensor.tvattmaskinen_aktiv"
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


def fetch_entity_history(
    secrets: dict[str, str],
    entity_id: str,
    end: datetime,
) -> list[tuple[datetime, str]]:
    end_param = urllib.parse.quote(end.isoformat())
    path = (
        f"/api/history/period/{end_param}"
        f"?filter_entity_id={urllib.parse.quote(entity_id)}"
        f"&minimal_response=true"
        f"&no_attributes=true"
    )
    raw = api_request(secrets, "GET", path)
    if not raw or not isinstance(raw, list) or not raw[0]:
        return []
    points: list[tuple[datetime, str]] = []
    for row in raw[0]:
        try:
            points.append((parse_iso(row["last_changed"]), str(row["state"])))
        except (KeyError, TypeError, ValueError):
            continue
    points.sort(key=lambda x: x[0])
    cutoff = end - timedelta(hours=LOOKBACK_HOURS)
    return [(t, s) for t, s in points if t >= cutoff]


def fetch_power_history(secrets: dict[str, str], end: datetime) -> list[tuple[datetime, float]]:
    rows = fetch_entity_history(secrets, POWER_ENTITY, end)
    out: list[tuple[datetime, float]] = []
    for t, state in rows:
        try:
            out.append((t, float(state)))
        except ValueError:
            continue
    return out


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


def find_run_window_from_active(
    active_points: list[tuple[datetime, str]],
    end: datetime,
) -> tuple[datetime, datetime] | None:
    """Senaste avslutade tvätt: off→on (aktiv) till on→off (klar), före end."""
    changes = [(t, s) for t, s in active_points if t <= end]
    if not changes:
        return None
    changes.sort(key=lambda x: x[0])

    run_end: datetime | None = None
    for i in range(len(changes) - 1, -1, -1):
        t, state = changes[i]
        if state == "off" and i > 0 and changes[i - 1][1] == "on":
            run_end = t
            break
    if run_end is None:
        return None

    run_start: datetime | None = None
    for i in range(len(changes) - 1, -1, -1):
        t, state = changes[i]
        if t > run_end:
            continue
        if state == "on" and i > 0 and changes[i - 1][1] == "off":
            run_start = t
            break
    if run_start is None:
        return None
    return run_start, run_end


def refine_power_start(
    power_points: list[tuple[datetime, float]],
    active_on: datetime,
    run_end: datetime,
) -> datetime:
    """binary_sensor.tvattmaskinen_aktiv har delay_on — backa till första märkbara effekt."""
    search_from = active_on - timedelta(minutes=15)
    first: datetime | None = None
    for t, v in power_points:
        if t < search_from or t > run_end:
            continue
        if v > LOW_W:
            first = t if first is None else min(first, t)
    return first if first is not None else active_on


def find_last_run_start(
    points: list[tuple[datetime, float]],
    end: datetime,
) -> datetime | None:
    """Reserv: första >= START_W efter minst IDLE_MINUTES med <= LOW_W före end."""
    if not points:
        return None
    idle_min_s = IDLE_MINUTES * 60
    last_low_at: datetime | None = None
    in_run = False
    run_start: datetime | None = None

    for t, v in points:
        if t > end:
            break
        if v <= LOW_W:
            last_low_at = t
            in_run = False
        elif v >= START_W:
            if not in_run:
                if last_low_at is not None and (t - last_low_at).total_seconds() >= idle_min_s:
                    run_start = t
                    in_run = True
                elif run_start is None and last_low_at is not None:
                    run_start = t
                    in_run = True
    return run_start


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


def write_log(message: str) -> None:
    try:
        LOG_PATH.write_text(message, encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    secrets = load_secrets()
    end = datetime.now().astimezone()
    try:
        points = fetch_power_history(secrets, end)
        slots = fetch_nordpool_slots(secrets)
        active_hist = fetch_entity_history(secrets, ACTIVE_ENTITY, end)
        window = find_run_window_from_active(active_hist, end)
        if window is not None:
            active_on, run_end = window
            start = refine_power_start(points, active_on, run_end)
        else:
            start = find_last_run_start(points, end)
            if start is None:
                set_cost_text(secrets, "")
                return 0
            run_end = find_last_run_end(points, start, end)
        if not slots:
            set_cost_text(secrets, "")
            return 0
        kwh, kr = integrate_cost(points, start, run_end, slots)
        if kr < 0.001 or kwh < 0.001:
            write_log(f"ingen kostnad start={start} end={run_end} kwh={kwh} kr={kr}")
            set_cost_text(secrets, "")
            return 0
        kr_text = format_kr(kr)
        set_cost_text(secrets, kr_text)
        msg = f"tvattmaskin kostnad: {kwh:.3f} kWh, {kr_text} kr (start={start.isoformat()}, end={run_end.isoformat()})"
        write_log(msg)
        print(msg)
        return 0
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError) as exc:
        write_log(f"fel: {exc!r}")
        print(f"tvattmaskin kostnad: fel {exc}", file=sys.stderr)
        try:
            set_cost_text(secrets, "")
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError):
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
