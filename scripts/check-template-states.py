#!/usr/bin/env python3
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

text = (ROOT / "templates.yaml").read_text(encoding="utf-8")
ids = re.findall(r"default_entity_id: ((?:sensor|binary_sensor)\.[a-z0-9_]+)", text)

unavail = []
ok = []
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

print(f"UNAVAILABLE: {len(unavail)}")
for row in unavail:
    print(" ", row)
print(f"OK: {len(ok)}")
