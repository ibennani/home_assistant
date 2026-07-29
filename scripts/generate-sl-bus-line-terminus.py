#!/usr/bin/env python3
"""Generera sl-bus-line-terminus.json från SL Journey Planner line-list."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

LINE_LIST_URL = (
    "https://journeyplanner.integration.sl.se/v2/line-list?line_list_subnetwork=tfs"
)
OUTPUT = Path(__file__).resolve().parents[1] / "www" / "sl-bus-line-terminus.json"


def main() -> None:
    with urllib.request.urlopen(LINE_LIST_URL, timeout=60) as response:
        payload = json.load(response)

    result: dict[str, dict[str, str]] = {}
    for entry in payload.get("transportations", []):
        if entry.get("product", {}).get("name") != "Buss":
            continue
        designation = str(entry.get("disassembledName") or "").strip()
        if not designation:
            continue
        entry_id = str(entry.get("id") or "")
        if ":R:" in entry_id:
            direction_code = "2"
        elif ":H:" in entry_id:
            direction_code = "1"
        else:
            continue
        destination = (entry.get("destination") or {}).get("name", "")
        terminus = destination.split(",")[0].replace("Stockholm, ", "").strip()
        result.setdefault(designation, {})[direction_code] = terminus

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Skrev {len(result)} busslinjer till {OUTPUT}")


if __name__ == "__main__":
    main()
