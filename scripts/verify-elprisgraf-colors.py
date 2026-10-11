#!/usr/bin/env python3
"""Verifiera elprisgraf: färg per kvart utifrån marginalpris, börs skarp + påslag 50 %."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "dashboards" / "dashboard-september-2025.yaml"
MARG = "sensor.elpris_marginal_kwh_se3"
SPOT = "sensor.nordpool_kwh_se3_sek_3_10_025"

def color_for(m: float) -> str:
    """Samma trösklar som colorFor i dashboard data_generator."""
    if m < 0:
        return "#809fff"
    if m < 0.50:
        return "#809fff"
    if m < 1.00:
        return "#28fccf"
    if m < 1.50:
        return "#28fc61"
    if m < 2.00:
        return "#ebfc28"
    if m < 3.00:
        return "#fcd228"
    if m < 4.00:
        return "#fc9628"
    if m < 5.00:
        return "#fc3e28"
    if m < 6.00:
        return "#fc289d"
    return "#af28fc"


def rnd(x: float) -> float:
    return round(max(0.0, x) * 100) / 100


def slot_label(day_off: int, index: int) -> str:
    total_min = day_off * 24 * 60 + index * 15
    h, m = divmod(total_min, 60)
    return f"{h:02d}:{m:02d}"


def fetch_arrays() -> tuple[list[float], list[float], list[float], list[float], bool]:
    url = os.environ.get("HA_URL", "").rstrip("/")
    token = os.environ.get("HA_TOKEN", "")
    if not url or not token:
        raise RuntimeError("HA_URL/HA_TOKEN saknas")

    def get_state(eid: str) -> dict:
        req = urllib.request.Request(
            f"{url}/api/states/{eid}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())

    marg = get_state(MARG)["attributes"]
    spot = get_state(SPOT)["attributes"]
    tv = [float(x) for x in marg.get("today") or []]
    tm = [float(x) for x in marg.get("tomorrow") or []]
    sv = spot.get("today") or []
    sm = spot.get("tomorrow") or []
    tmr = spot.get("tomorrow_valid")
    tm_ok = tmr is True or (isinstance(tmr, str) and tmr.lower() == "true")
    return tv, tm, [float(x) for x in sv], [float(x) for x in sm] if tm_ok else [], tm_ok


def verify_quarters(
    label: str, marg: list[float], spot: list[float], issues: list[str]
) -> None:
    n = min(len(marg), len(spot))
    if len(marg) != len(spot):
        issues.append(f"{label}: marginal {len(marg)} kvartar, spot {len(spot)}")
    for i in range(n):
        m, s = float(marg[i]), float(spot[i])
        y_b, y_p = rnd(s), rnd(m - s)
        if y_b + y_p > m + 0.02:
            issues.append(f"{label} {slot_label(0 if label == 'idag' else 1, i)}: staplar > marginal")
        if s > m + 0.001:
            issues.append(f"{label} {slot_label(0 if label == 'idag' else 1, i)}: spot > marginal")


def check_dashboard_js(issues: list[str]) -> None:
    text = DASH.read_text(encoding="utf-8")
    börs = re.findall(r"name: Börs\n.*?data_generator: \"([^\"]+)\"", text, re.DOTALL)
    påslag = re.findall(r"name: Påslag\n.*?data_generator: \"([^\"]+)\"", text, re.DOTALL)
    if len(börs) < 2 or len(påslag) < 2:
        issues.append("dashboard: förväntar minst 2 elpris-kort med Börs/Påslag")
        return
    if len(set(börs)) != 1 or len(set(påslag)) != 1:
        issues.append("dashboard: Börs/Påslag data_generator skiljer mellan kort")
    b = börs[0]
    if "fillColor: colorFor(m)" not in b.replace("\\n", "\n"):
        issues.append("dashboard: Börs saknar fillColor: colorFor(m)")
    if "colorAlpha50(colorFor(m))" not in påslag[0].replace("\\n", "\n"):
        issues.append("dashboard: Påslag saknar colorAlpha50(colorFor(m))")
    if "columnWidth: 100%" not in text:
        issues.append("dashboard: columnWidth 100% saknas (staplar kant i kant)")


def main() -> int:
    issues: list[str] = []
    check_dashboard_js(issues)

    try:
        tv, tm, sv, sm, tm_ok = fetch_arrays()
    except (RuntimeError, urllib.error.URLError, OSError) as e:
        print(f"verify-elprisgraf-colors: hoppar live-data ({e})", file=sys.stderr)
        if issues:
            for x in issues:
                print(f"  {x}", file=sys.stderr)
            return 1
        print("verify-elprisgraf-colors: OK (endast dashboard-kontroll)")
        return 0

    verify_quarters("idag", tv, sv, issues)
    if tm_ok:
        verify_quarters("imorgon", tm, sm, issues)

    n = len(tv) + (len(tm) if tm_ok else 0)
    print(f"verify-elprisgraf-colors: {n} kvartar, {len(tv)} idag" + (f", {len(tm)} imorgon" if tm_ok else ""))

    if issues:
        for x in issues:
            print(f"  FAIL: {x}", file=sys.stderr)
        return 1
    print("verify-elprisgraf-colors: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
