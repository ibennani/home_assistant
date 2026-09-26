#!/usr/bin/env python3
"""Hämta faktiska kvartspriser från Tibber (tibber.get_prices) till HA-sensor.

Priset från Tibber är total kr/kWh per intervall (det kunden betalar).
Uppdaterar sensor.elpris_faktisk_kwh_se3 som marginal-sensorn läser.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SECRETS_PATH = __import__("pathlib").Path("/config/secrets.yaml")
LOG_PATH = __import__("pathlib").Path("/config/www/elpris-tibber-sync.log")
FAKTISK_ENTITY = "sensor.elpris_faktisk_kwh_se3"
TIBBER_PRICE_ENTITY = "sensor.electricity_price_eksharadsgatan_6"
TZ = ZoneInfo("Europe/Stockholm")
SLOTS_PER_DAY = 96


def log(msg: str) -> None:
    line = f"{datetime.now(TZ).isoformat()} {msg}\n"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


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
        or os.environ.get("HASSIO_TOKEN", "").strip()
    )
    base = secrets.get("ha_internal_url", "http://127.0.0.1:8123").rstrip("/")
    if token and not secrets.get("ha_long_lived_token") and os.environ.get("SUPERVISOR_TOKEN"):
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def ha_service_call(secrets: dict[str, str], domain: str, service: str, data: dict) -> object:
    payload = dict(data)
    payload["return_response"] = True
    try:
        return api_request(secrets, "POST", f"/api/services/{domain}/{service}", payload)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        pass
    try:
        result = subprocess.run(
            ["ha", "service", "call", f"{domain}.{service}", json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.SubprocessError, OSError):
        pass
    return {}


def parse_tibber_time(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def floor_quarter(dt: datetime) -> datetime:
    dt = dt.astimezone(TZ)
    minute = (dt.minute // 15) * 15
    return dt.replace(minute=minute, second=0, microsecond=0)


def extract_prices_payload(resp: object) -> dict[str, list[dict]]:
    if isinstance(resp, list) and resp:
        first = resp[0]
        if isinstance(first, dict):
            resp = first
    if not isinstance(resp, dict):
        return {}
    if isinstance(resp.get("prices"), dict):
        return resp["prices"]
    for key in ("response", "service_response"):
        inner = resp.get(key)
        if isinstance(inner, dict) and isinstance(inner.get("prices"), dict):
            return inner["prices"]
    return {}


def pick_home_key(prices: dict[str, list], nickname: str) -> str | None:
    if not prices:
        return None
    nick_l = nickname.strip().lower()
    for key in prices:
        if key.strip().lower() == nick_l:
            return key
    for key in prices:
        if nick_l in key.strip().lower() or key.strip().lower() in nick_l:
            return key
    return next(iter(prices.keys()), None)


def build_day(
    day_start: datetime,
    price_map: dict[datetime, float],
) -> tuple[list[float], list[dict]]:
    values: list[float] = []
    raw: list[dict] = []
    for i in range(SLOTS_PER_DAY):
        slot_start = day_start + timedelta(minutes=15 * i)
        slot_end = slot_start + timedelta(minutes=15)
        price = price_map.get(floor_quarter(slot_start))
        if price is None:
            price = 0.0
        values.append(round(price, 4))
        raw.append(
            {
                "start": slot_start.isoformat(),
                "end": slot_end.isoformat(),
                "value": round(price, 4),
            }
        )
    return values, raw


def current_slot_price(price_map: dict[datetime, float], now: datetime) -> float:
    key = floor_quarter(now)
    if key in price_map:
        return float(price_map[key])
    for delta in (0, -15, 15, -30, 30):
        k = key + timedelta(minutes=delta)
        if k in price_map:
            return float(price_map[k])
    return 0.0


def main() -> int:
    secrets = load_secrets()
    try:
        nick_state = api_request(secrets, "GET", f"/api/states/{TIBBER_PRICE_ENTITY}")
        attrs = nick_state.get("attributes", {}) if isinstance(nick_state, dict) else {}
        nickname = str(attrs.get("app_nickname") or "Ekshäradsgatan 6")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError, TypeError):
        nickname = "Ekshäradsgatan 6"

    now = datetime.now(TZ)
    range_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    range_end = range_start + timedelta(days=2)

    resp = ha_service_call(
        secrets,
        "tibber",
        "get_prices",
        {
            "start": range_start.strftime("%Y-%m-%d %H:%M:%S"),
            "end": range_end.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    prices_by_home = extract_prices_payload(resp)
    home_key = pick_home_key(prices_by_home, nickname)
    if not home_key:
        log("ingen Tibber-hemnyckel i svar")
        return 1

    price_map: dict[datetime, float] = {}
    for row in prices_by_home.get(home_key, []):
        if not isinstance(row, dict):
            continue
        st = row.get("start_time")
        pr = row.get("price")
        if st is None or pr is None:
            continue
        try:
            price_map[floor_quarter(parse_tibber_time(str(st)))] = float(pr)
        except (TypeError, ValueError):
            continue

    if len(price_map) < 4:
        log(f"för få Tibber-priser: {len(price_map)}")
        return 1

    today_start = range_start
    tomorrow_start = range_start + timedelta(days=1)
    today_vals, raw_today = build_day(today_start, price_map)
    tomorrow_vals, raw_tomorrow = build_day(tomorrow_start, price_map)

    nonzero_tomorrow = sum(1 for v in tomorrow_vals if v > 0.01)
    tomorrow_valid = nonzero_tomorrow >= 90

    state_val = round(current_slot_price(price_map, now), 3)
    if state_val <= 0:
        state_val = round(float(today_vals[max(0, ((now.hour * 60 + now.minute) // 15))]), 3)

    body = {
        "state": str(state_val),
        "attributes": {
            "unit_of_measurement": "SEK/kWh",
            "device_class": "monetary",
            "friendly_name": "Elpris faktisk kWh (Tibber)",
            "source": "tibber.get_prices",
            "sync_ok": True,
            "synced_at": now.isoformat(),
            "home": home_key,
            "today": today_vals,
            "tomorrow": tomorrow_vals if tomorrow_valid else [],
            "raw_today": raw_today,
            "raw_tomorrow": raw_tomorrow if tomorrow_valid else [],
            "tomorrow_valid": tomorrow_valid,
            "slots_tibber": len(price_map),
        },
    }
    api_request(secrets, "POST", f"/api/states/{urllib.parse.quote(FAKTISK_ENTITY, safe='')}", body)
    log(f"OK state={state_val} today={len(today_vals)} tibber_slots={len(price_map)} tomorrow_valid={tomorrow_valid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
