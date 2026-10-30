#!/usr/bin/env python3
"""Beräkna elkostnad per kvart för rullande 48 timmar (kr + kWh per 15 min)."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SECRETS_PATH = Path("/config/secrets.yaml")
RECORDER_DB = Path("/config/home-assistant_v2.db")
STATE_ENTITY = "sensor.el_kostnad_24h_kvartar_runner"
POWER_ENTITY = "sensor.power_eksharadsgatan_6"
ELPRIS_ENTITY = "sensor.elpris_marginal_kwh_se3"
TIBBER_PRICE_ENTITY = "sensor.electricity_price_eksharadsgatan_6"
TZ = ZoneInfo("Europe/Stockholm")
HOURS_BACK = 48
QUARTERS = HOURS_BACK * 4


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


def load_supervisor_token() -> str:
    for key in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    env_dir = __import__("pathlib").Path("/run/s6/container_environment")
    if env_dir.is_dir():
        for name in ("SUPERVISOR_TOKEN", "HASSIO_TOKEN"):
            path = env_dir / name
            if path.is_file():
                try:
                    return path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
    return ""


def ha_auth(secrets: dict[str, str]) -> tuple[str, str]:
    long_lived = secrets.get("ha_long_lived_token", "").strip()
    token = (
        long_lived
        or os.environ.get("HA_TOKEN", "").strip()
        or os.environ.get("SUPERVISOR_TOKEN", "").strip()
        or os.environ.get("HASSIO_TOKEN", "").strip()
        or load_supervisor_token()
    )
    if not token:
        raise RuntimeError("saknar HA-token")
    base = secrets.get("ha_internal_url", "http://127.0.0.1:8123").rstrip("/")
    if Path("/config/configuration.yaml").exists() and (
        "ui.nabu.casa" in base or base.startswith("https://")
    ):
        base = "http://127.0.0.1:8123"
    elif token and not long_lived and (
        os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
    ):
        base = "http://supervisor/core"
    return base, token


def api_request(
    secrets: dict[str, str],
    method: str,
    path: str,
    body: dict | None = None,
) -> object:
    base, token = ha_auth(secrets)
    if not token:
        raise RuntimeError("saknar HA-token")
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def floor_quarter(dt: datetime) -> datetime:
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


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


def fetch_state_attributes_db(entity_id: str) -> dict:
    if not RECORDER_DB.is_file():
        return {}
    try:
        with sqlite3.connect(f"file:{RECORDER_DB}?mode=ro", uri=True, timeout=15) as conn:
            row = conn.execute(
                """
                SELECT s.attributes
                FROM states s
                INNER JOIN states_meta m ON s.metadata_id = m.metadata_id
                WHERE m.entity_id = ?
                ORDER BY s.last_updated_ts DESC
                LIMIT 1
                """,
                (entity_id,),
            ).fetchone()
    except sqlite3.Error:
        return {}
    if not row or not row[0]:
        return {}
    try:
        parsed = json.loads(row[0])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def fetch_state_db(entity_id: str) -> dict:
    if not RECORDER_DB.is_file():
        return {}
    try:
        with sqlite3.connect(f"file:{RECORDER_DB}?mode=ro", uri=True, timeout=15) as conn:
            row = conn.execute(
                """
                SELECT s.state, s.attributes
                FROM states s
                INNER JOIN states_meta m ON s.metadata_id = m.metadata_id
                WHERE m.entity_id = ?
                ORDER BY s.last_updated_ts DESC
                LIMIT 1
                """,
                (entity_id,),
            ).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    state, attrs_raw = row[0], row[1]
    attrs: dict = {}
    if attrs_raw:
        try:
            parsed = json.loads(attrs_raw)
            if isinstance(parsed, dict):
                attrs = parsed
        except json.JSONDecodeError:
            attrs = {}
    return {"state": state, "attributes": attrs}


def marginal_slots_from_attrs(attrs: dict) -> list[tuple[datetime, datetime, float]]:
    slots: list[tuple[datetime, datetime, float]] = []
    for key in ("raw_today", "raw_tomorrow"):
        if key == "raw_tomorrow":
            tmr = attrs.get("tomorrow_valid")
            tm_ok = tmr is True or (isinstance(tmr, str) and tmr.lower() == "true")
            if not tm_ok:
                continue
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
    return sorted(slots, key=lambda x: x[0])


def fetch_marginal_slots(secrets: dict[str, str]) -> list[tuple[datetime, datetime, float]]:
    attrs: dict = {}
    if Path("/config/configuration.yaml").exists():
        attrs = fetch_state_attributes_db(ELPRIS_ENTITY)
    has_raw = bool(coerce_slot_list(attrs.get("raw_today"))) or bool(
        coerce_slot_list(attrs.get("today"))
    )
    if not has_raw:
        try:
            resp = api_request(secrets, "GET", f"/api/states/{ELPRIS_ENTITY}")
            if isinstance(resp, dict):
                api_attrs = resp.get("attributes")
                if isinstance(api_attrs, dict):
                    attrs = api_attrs
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
            pass
    if not attrs:
        db_state = fetch_state_db(ELPRIS_ENTITY)
        if isinstance(db_state.get("attributes"), dict):
            attrs = db_state["attributes"]
    return marginal_slots_from_attrs(attrs)


def extract_prices_payload(resp: object) -> dict[str, list]:
    if not isinstance(resp, dict):
        return {}
    svc = resp.get("service_response") or resp.get("response") or resp
    if isinstance(svc, dict):
        for val in svc.values():
            if isinstance(val, dict):
                return val
    return svc if isinstance(svc, dict) else {}


def pick_home_key(prices_by_home: dict, nickname: str) -> str | None:
    if not prices_by_home:
        return None
    nick = nickname.lower()
    for key in prices_by_home:
        if nick in str(key).lower():
            return str(key)
    return next(iter(prices_by_home.keys()), None)


def fetch_tibber_price_map(
    secrets: dict[str, str], range_start: datetime, range_end: datetime
) -> dict[datetime, float]:
    try:
        nick_state = api_request(secrets, "GET", f"/api/states/{TIBBER_PRICE_ENTITY}")
        attrs = nick_state.get("attributes", {}) if isinstance(nick_state, dict) else {}
        nickname = str(attrs.get("app_nickname") or "Ekshäradsgatan 6")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        nickname = "Ekshäradsgatan 6"
    payload = {
        "start": range_start.astimezone(TZ).isoformat(),
        "end": range_end.astimezone(TZ).isoformat(),
        "return_response": True,
    }
    resp = api_request(
        secrets,
        "POST",
        "/api/services/tibber/get_prices",
        payload,
    )
    prices_by_home = extract_prices_payload(resp)
    home_key = pick_home_key(prices_by_home, nickname)
    if not home_key:
        return {}
    price_map: dict[datetime, float] = {}
    for row in prices_by_home.get(home_key, []):
        if not isinstance(row, dict):
            continue
        st = row.get("start_time")
        pr = row.get("price")
        if st is None or pr is None:
            continue
        try:
            price_map[floor_quarter(parse_iso(str(st)))] = float(pr)
        except (TypeError, ValueError):
            continue
    return price_map


def merge_price_slots(
    marginal: list[tuple[datetime, datetime, float]],
    tibber_map: dict[datetime, float],
    window_start: datetime,
    window_end: datetime,
    fallback_price: float,
) -> list[tuple[datetime, datetime, float]]:
    by_start: dict[datetime, tuple[datetime, datetime, float]] = {
        s0: (s0, s1, p) for s0, s1, p in marginal
    }
    last_price = fallback
    t = floor_quarter(window_start)
    while t < window_end + timedelta(minutes=15):
        if t in by_start:
            last_price = by_start[t][2]
        else:
            price = tibber_map.get(t)
            if price is None:
                for delta in (0, -15, 15, -30, 30, -45, 45):
                    key = t + timedelta(minutes=delta)
                    if key in tibber_map:
                        price = tibber_map[key]
                        break
            if price is None or price <= 0:
                price = last_price if last_price > 0 else fallback
            by_start[t] = (t, t + timedelta(minutes=15), float(price))
            last_price = float(price)
        t += timedelta(minutes=15)
    return sorted(by_start.values(), key=lambda x: x[0])


def fetch_power_history_db(
    start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    if not RECORDER_DB.is_file():
        return []
    cutoff_ts = start.timestamp()
    try:
        with sqlite3.connect(f"file:{RECORDER_DB}?mode=ro", uri=True, timeout=30) as conn:
            rows = conn.execute(
                """
                SELECT s.last_updated_ts, s.state
                FROM states s
                INNER JOIN states_meta m ON s.metadata_id = m.metadata_id
                WHERE m.entity_id = ? AND s.last_updated_ts >= ?
                ORDER BY s.last_updated_ts
                """,
                (POWER_ENTITY, cutoff_ts),
            ).fetchall()
    except sqlite3.Error:
        return []
    points: list[tuple[datetime, float]] = []
    tz = start.tzinfo or TZ
    for ts, state in rows:
        try:
            t = datetime.fromtimestamp(float(ts), tz=tz)
            v = float(state)
        except (TypeError, ValueError):
            continue
        if t > end or v < 0:
            continue
        points.append((t, v))
    return points


def fetch_power_history(
    secrets: dict[str, str], start: datetime, end: datetime
) -> list[tuple[datetime, float]]:
    points: list[tuple[datetime, float]] = []
    try:
        start_param = urllib.parse.quote(start.isoformat())
        path = (
            f"/api/history/period/{start_param}"
            f"?filter_entity_id={urllib.parse.quote(POWER_ENTITY)}"
            f"&minimal_response=true"
            f"&no_attributes=true"
        )
        data = api_request(secrets, "GET", path)
        if isinstance(data, list) and data and isinstance(data[0], list):
            entity_rows = data[0]
            for row in entity_rows:
                if not isinstance(row, dict):
                    continue
                try:
                    t = parse_iso(str(row.get("last_changed") or row.get("last_updated")))
                    v = float(row.get("state"))
                except (TypeError, ValueError):
                    continue
                if t > end or v < 0:
                    continue
                points.append((t, v))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        points = []
    if not points:
        points = fetch_power_history_db(start, end)
    points.sort(key=lambda x: x[0])
    return points


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
) -> tuple[float, float, float | None]:
    """Returnerar (kWh, kostnad_kr, representativt_pris_kr_per_kwh)."""
    if end <= start:
        return 0.0, 0.0, price_at(slots, start)
    series = [(t, v) for t, v in points if start <= t <= end]
    if not series:
        series = [(t, v) for t, v in points if t <= end]
    if not series:
        return 0.0, 0.0, price_at(slots, start)
    if series[0][0] > start:
        prev = next((v for t, v in reversed(points) if t <= start), series[0][1])
        series.insert(0, (start, prev))
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
    rep = price_at(slots, start)
    if rep is None and total_kwh > 0:
        rep = total_kr / total_kwh
    return total_kwh, total_kr, rep


def compute_payload(secrets: dict[str, str]) -> dict:
    now = datetime.now(TZ)
    window_start = floor_quarter(now - timedelta(hours=HOURS_BACK))
    window_end = now
    try:
        marginal = fetch_marginal_slots(secrets)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        marginal = []
    fallback = 0.0
    try:
        st = api_request(secrets, "GET", f"/api/states/{ELPRIS_ENTITY}")
        if isinstance(st, dict):
            fallback = float(st.get("state") or 0)
    except (TypeError, ValueError, urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError):
        db_st = fetch_state_db(ELPRIS_ENTITY)
        try:
            fallback = float(db_st.get("state") or 0)
        except (TypeError, ValueError):
            fallback = 0.0
    tibber_map: dict[datetime, float] = {}
    try:
        tibber_map = fetch_tibber_price_map(
            secrets, window_start - timedelta(hours=1), window_end + timedelta(hours=1)
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        tibber_map = {}
    price_slots = merge_price_slots(
        marginal, tibber_map, window_start, window_end, fallback
    )
    try:
        power = fetch_power_history(
            secrets, window_start - timedelta(minutes=5), window_end
        )
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        power = []

    slots_out: list[dict] = []
    total_kr = 0.0
    t = window_start
    for _ in range(QUARTERS):
        if t >= window_end:
            break
        slot_end = min(t + timedelta(minutes=15), window_end)
        kwh, kr, price = integrate_cost(power, t, slot_end, price_slots)
        total_kr += kr
        if kwh > 0.0001:
            slot_price = round(kr / kwh, 2)
        else:
            slot_price = round(float(price or fallback), 2)
        slots_out.append(
            {
                "start": t.isoformat(),
                "end": slot_end.isoformat(),
                "kwh": round(kwh, 4),
                "price": slot_price,
                "cost": round(kr, 2),
            }
        )
        t += timedelta(minutes=15)

    return {
        "total": round(total_kr, 2),
        "total_kr": round(total_kr, 2),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "slots": slots_out,
        "updated_at": now.isoformat(),
        "method": "effekt_marginalpris",
    }


def run_self_test() -> int:
    slots = [
        (
            datetime(2026, 1, 1, 0, 0, tzinfo=TZ),
            datetime(2026, 1, 1, 0, 15, tzinfo=TZ),
            1.0,
        )
    ]
    pts = [
        (datetime(2026, 1, 1, 0, 0, tzinfo=TZ), 1000.0),
        (datetime(2026, 1, 1, 0, 15, tzinfo=TZ), 1000.0),
    ]
    kwh, kr, _ = integrate_cost(
        pts,
        datetime(2026, 1, 1, 0, 0, tzinfo=TZ),
        datetime(2026, 1, 1, 0, 15, tzinfo=TZ),
        slots,
    )
    assert abs(kwh - 0.25) < 0.001, kwh
    assert abs(kr - 0.25) < 0.01, kr
    assert floor_quarter(datetime(2026, 3, 4, 13, 7, 30, tzinfo=TZ)) == datetime(
        2026, 3, 4, 13, 0, 0, tzinfo=TZ
    )
    return 0


def publish_state(secrets: dict[str, str], payload: dict) -> None:
    body = {
        "state": str(payload.get("total", 0.0)),
        "attributes": {
            "unit_of_measurement": "SEK",
            "device_class": "monetary",
            "friendly_name": "El kostnad 24h kvartar runner",
            "total": payload.get("total", 0.0),
            "total_kr": payload.get("total_kr", 0.0),
            "slots": payload.get("slots", []),
            "window_start": payload.get("window_start"),
            "window_end": payload.get("window_end"),
            "updated_at": payload.get("updated_at"),
            "method": payload.get("method"),
        },
    }
    entity = urllib.parse.quote(STATE_ENTITY, safe="")
    api_request(secrets, "POST", f"/api/states/{entity}", body)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return run_self_test()
    secrets = load_secrets()
    try:
        payload = compute_payload(secrets)
    except Exception as exc:
        payload = {
            "total": 0.0,
            "total_kr": 0.0,
            "slots": [],
            "updated_at": datetime.now(TZ).isoformat(),
            "method": "fel",
            "error": str(exc)[:240],
        }
    else:
        try:
            publish_state(secrets, payload)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
            pass
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
