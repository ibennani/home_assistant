#!/usr/bin/env python3
"""Verifiera template-entiteter mot live HA (läser includes/template.yaml)."""
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# unique_id -> entity_id när slug inte följer unique_id
ENTITY_OVERRIDES = {
    "julbelysningen": "binary_sensor.julbelysning",
    "05s6df0a1sg0asg8dd1asgr1aaasgddda": "sensor.ljusstyrka_framsidan_maximal",
    "indoor_pressure_mean_05s6df0a1sg0asg81asg8r00aaasdf": "sensor.lufttryck_inomhus",
    "indoor_pressure_min_05s6df0a1sg0asg81asg8r0aasgsa": "sensor.lufttryck_inomhus_min",
    "indoor_pressure_max_05s6df0a1sg0asg8dd1asgr1aaasg": "sensor.lufttryck_inomhus_max",
    "belysning_energi_totalt_kwh": "sensor.belysning_energi_totalt",
    "belysning_energiforbrukning_just_nu": "sensor.belysning_energiforbrukning_just_nu",
    "belysning_energi_unavailable_count": "sensor.belysning_energi_unavailable_count",
}


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def entity_ids_from_includes_template() -> list[str]:
    text = (ROOT / "includes" / "template.yaml").read_text(encoding="utf-8")
    domain = "sensor"
    ids: list[str] = []

    for line in text.splitlines():
        if re.match(r"^- sensor:\s*$", line):
            domain = "sensor"
            continue
        if re.match(r"^- binary_sensor:\s*$", line):
            domain = "binary_sensor"
            continue
        if re.match(r"^\s+sensor:\s*$", line):
            domain = "sensor"
            continue
        if re.match(r"^\s+binary_sensor:\s*$", line):
            domain = "binary_sensor"
            continue

        m = re.match(r"^\s+unique_id:\s*(\S+)\s*$", line)
        if not m:
            continue

        uid = m.group(1)
        eid = ENTITY_OVERRIDES.get(uid, f"{domain}.{uid}")
        if eid not in ids:
            ids.append(eid)

    return ids


def main() -> None:
    env = load_env()
    ids = entity_ids_from_includes_template()
    unavail: list[tuple] = []
    ok: list[tuple] = []

    for eid in ids:
        req = urllib.request.Request(
            f"{env['HA_URL']}/api/states/{eid}",
            headers={"Authorization": f"Bearer {env['HA_TOKEN']}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                st = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            unavail.append((eid, f"HTTP {e.code}"))
            continue

        state = st.get("state")
        restored = st.get("attributes", {}).get("restored", False)
        if state in ("unavailable", "unknown") or restored:
            unavail.append((eid, state, restored))
        else:
            ok.append((eid, state))

    print(f"Källa: includes/template.yaml ({len(ids)} entiteter)")
    print(f"UNAVAILABLE: {len(unavail)}")
    for row in unavail:
        print(" ", row)
    print(f"OK: {len(ok)}")


if __name__ == "__main__":
    main()
