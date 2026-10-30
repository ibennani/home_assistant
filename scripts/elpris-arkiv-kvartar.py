#!/usr/bin/env python3
"""Arkivera marginal-elpris per kvart på disk (rullande 8 kalenderdagar)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ARCHIVE_DIR = Path("/config/data/elpris-kvartar")
LOG_PATH = Path("/config/www/elpris-arkiv.log")
SECRETS_PATH = Path("/config/secrets.yaml")
ELPRIS_ENTITY = "sensor.elpris_marginal_kwh_se3"
TZ = ZoneInfo("Europe/Stockholm")
KEEP_DAYS_BACK = 7
SLOTS_PER_DAY = 96
MIN_SLOTS_LOCK = 90


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
    if Path("/config/configuration.yaml").exists() and (
        "ui.nabu.casa" in base or base.startswith("https://")
    ):
        base = "http://127.0.0.1:8123"
    elif token and not secrets.get("ha_long_lived_token") and os.environ.get("SUPERVISOR_TOKEN"):
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
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
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


def fetch_marginal_attributes(secrets: dict[str, str]) -> dict:
    try:
        resp = api_request(secrets, "GET", f"/api/states/{ELPRIS_ENTITY}")
        if isinstance(resp, dict):
            attrs = resp.get("attributes")
            return attrs if isinstance(attrs, dict) else {}
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, ValueError):
        pass
    return {}


def slots_from_raw_rows(rows: list) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start_raw = row.get("start")
        end_raw = row.get("end")
        val = row.get("value")
        if start_raw is None or end_raw is None or val is None:
            continue
        try:
            start = parse_iso(str(start_raw))
            end = parse_iso(str(end_raw))
            price = round(float(val), 4)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        out.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "value": price,
            }
        )
    return out


def slots_from_today_list(today: list, day: date) -> list[dict]:
    if not today:
        return []
    step = 15 if len(today) > 24 else 60
    midnight = datetime.combine(day, datetime.min.time(), tzinfo=TZ)
    out: list[dict] = []
    for i, val in enumerate(today):
        try:
            price = round(float(val), 4)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        start = midnight + timedelta(minutes=i * step)
        end = start + timedelta(minutes=step)
        out.append({"start": start.isoformat(), "end": end.isoformat(), "value": price})
    return out


def collect_marginal_day_slots(attrs: dict) -> dict[str, list[dict]]:
    by_day: dict[str, list[dict]] = {}
    raw_today = slots_from_raw_rows(coerce_slot_list(attrs.get("raw_today")))
    raw_tomorrow = slots_from_raw_rows(coerce_slot_list(attrs.get("raw_tomorrow")))
    tmr = attrs.get("tomorrow_valid")
    tm_ok = tmr is True or (isinstance(tmr, str) and tmr.lower() == "true")

    for slot in raw_today:
        day_key = parse_iso(slot["start"]).date().isoformat()
        by_day.setdefault(day_key, []).append(slot)
    if tm_ok:
        for slot in raw_tomorrow:
            day_key = parse_iso(slot["start"]).date().isoformat()
            by_day.setdefault(day_key, []).append(slot)

    today_list = coerce_slot_list(attrs.get("today"))
    if today_list:
        day_key = datetime.now(TZ).date().isoformat()
        if day_key not in by_day or len(by_day[day_key]) < SLOTS_PER_DAY // 2:
            by_day[day_key] = slots_from_today_list(today_list, datetime.now(TZ).date())

    if tm_ok:
        tomorrow_list = coerce_slot_list(attrs.get("tomorrow"))
        if tomorrow_list:
            tday = (datetime.now(TZ).date() + timedelta(days=1)).isoformat()
            if tday not in by_day or len(by_day[tday]) < SLOTS_PER_DAY // 2:
                by_day[tday] = slots_from_today_list(
                    tomorrow_list, datetime.now(TZ).date() + timedelta(days=1)
                )
    return by_day


def day_path(day: date) -> Path:
    return ARCHIVE_DIR / f"{day.isoformat()}.json"


def load_day_file(day: date) -> dict:
    path = day_path(day)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def merge_slots(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_start: dict[str, dict] = {}
    for row in existing:
        if isinstance(row, dict) and row.get("start"):
            by_start[str(row["start"])] = row
    for row in incoming:
        if isinstance(row, dict) and row.get("start"):
            by_start[str(row["start"])] = row
    merged = sorted(by_start.values(), key=lambda r: str(r.get("start", "")))
    return merged


def write_day_file(
    day: date,
    slots: list[dict],
    source: str,
    locked: bool | None = None,
) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_day_file(day)
    if existing.get("locked") is True and locked is not True:
        return len(coerce_slot_list(existing.get("slots")))
    merged = merge_slots(coerce_slot_list(existing.get("slots")), slots)
    payload = {
        "date": day.isoformat(),
        "timezone": str(TZ),
        "source": source,
        "locked": bool(existing.get("locked")) if locked is None else bool(locked),
        "updated_at": datetime.now(TZ).isoformat(),
        "slots": merged,
    }
    day_path(day).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(merged)


def purge_old_files(today: date | None = None) -> int:
    today = today or datetime.now(TZ).date()
    cutoff = today - timedelta(days=KEEP_DAYS_BACK)
    removed = 0
    if not ARCHIVE_DIR.is_dir():
        return 0
    for path in ARCHIVE_DIR.glob("*.json"):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def sync_from_marginal(secrets: dict[str, str]) -> dict:
    attrs = fetch_marginal_attributes(secrets)
    source = str(attrs.get("price_source") or "marginal")
    by_day = collect_marginal_day_slots(attrs)
    today = datetime.now(TZ).date()
    written: dict[str, int] = {}
    for offset in range(-KEEP_DAYS_BACK, 2):
        day = today + timedelta(days=offset)
        if day.isoformat() in by_day:
            n = write_day_file(day, by_day[day.isoformat()], source=source)
            written[day.isoformat()] = n
    removed = purge_old_files(today)
    return {"written": written, "removed_old_files": removed, "source": source}


def tick_current_quarter(secrets: dict[str, str]) -> dict:
    attrs = fetch_marginal_attributes(secrets)
    source = str(attrs.get("price_source") or "marginal")
    now = datetime.now(TZ)
    slot_start = floor_quarter(now)
    slot_end = slot_start + timedelta(minutes=15)
    price: float | None = None

    for row in slots_from_raw_rows(coerce_slot_list(attrs.get("raw_today"))):
        st = parse_iso(row["start"])
        en = parse_iso(row["end"])
        if st <= slot_start < en:
            price = float(row["value"])
            break

    if price is None:
        today_list = coerce_slot_list(attrs.get("today"))
        if today_list:
            idx = (slot_start.hour * 60 + slot_start.minute) // 15
            if 0 <= idx < len(today_list):
                try:
                    price = float(today_list[idx])
                except (TypeError, ValueError):
                    price = None

    if price is None or price <= 0:
        try:
            price = float(attrs.get("state") or 0)
        except (TypeError, ValueError):
            price = None
    if price is None or price <= 0:
        return {"ok": False, "reason": "inget pris för aktuellt kvart"}

    day = slot_start.date()
    row = {
        "start": slot_start.isoformat(),
        "end": slot_end.isoformat(),
        "value": round(price, 4),
    }
    n = write_day_file(day, [row], source=source)
    purge_old_files(day)
    return {"ok": True, "day": day.isoformat(), "slot": row["start"], "price": row["value"], "slots_in_file": n}


def lock_yesterday() -> dict:
    today = datetime.now(TZ).date()
    yday = today - timedelta(days=1)
    data = load_day_file(yday)
    slots = coerce_slot_list(data.get("slots"))
    if len(slots) < MIN_SLOTS_LOCK:
        return {"ok": False, "day": yday.isoformat(), "slots": len(slots)}
    n = write_day_file(yday, slots, source=str(data.get("source") or "marginal"), locked=True)
    purge_old_files(today)
    return {"ok": True, "day": yday.isoformat(), "locked": True, "slots": n}


def run_self_test() -> int:
    tmp = Path("/tmp/elpris-arkiv-test")
    tmp.mkdir(parents=True, exist_ok=True)
    global ARCHIVE_DIR
    old = ARCHIVE_DIR
    ARCHIVE_DIR = tmp
    try:
        d = date(2026, 1, 1)
        write_day_file(
            d,
            [{"start": "2026-01-01T00:00:00+01:00", "end": "2026-01-01T00:15:00+01:00", "value": 1.0}],
            "test",
        )
        write_day_file(
            d,
            [{"start": "2026-01-01T00:15:00+01:00", "end": "2026-01-01T00:30:00+01:00", "value": 2.0}],
            "test",
        )
        data = load_day_file(d)
        assert len(coerce_slot_list(data.get("slots"))) == 2
        merged = merge_slots([], [{"start": "2026-01-01T00:00:00+01:00", "end": "x", "value": 3}])
        assert merged[0]["value"] == 3
    finally:
        ARCHIVE_DIR = old
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Arkivera elpris per kvart")
    parser.add_argument("--tick", action="store_true", help="Uppdatera endast aktuellt kvart")
    parser.add_argument("--lock-yesterday", action="store_true", help="Lås gårdagens fil")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    secrets = load_secrets()
    try:
        if args.lock_yesterday:
            result = lock_yesterday()
        elif args.tick:
            result = tick_current_quarter(secrets)
        else:
            result = sync_from_marginal(secrets)
    except Exception as exc:
        log(f"FEL {exc}")
        print(json.dumps({"ok": False, "error": str(exc)[:200]}, ensure_ascii=False))
        return 1

    log(json.dumps(result, ensure_ascii=False))
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
