#!/usr/bin/env python3
"""Hämta SL:s site-lista och spara minimal cache till www/sl-sites.json."""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

API_URL = "https://transport.integration.sl.se/v1/sites"
OUTPUT = Path(__file__).resolve().parents[1] / "www" / "sl-sites.json"
TEST_SITE_RE = re.compile(r"^Test\s*\d+$", re.IGNORECASE)


def is_test_site(site: dict) -> bool:
    name = str(site.get("name") or "").strip()
    return bool(TEST_SITE_RE.match(name))


def main() -> int:
    with urllib.request.urlopen(API_URL, timeout=60) as response:
        sites = json.load(response)

    minimal = [
        {
            "id": site["id"],
            "name": site["name"],
            "lat": site["lat"],
            "lon": site["lon"],
        }
        for site in sites
        if site.get("lat") is not None
        and site.get("lon") is not None
        and not is_test_site(site)
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(minimal, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Skrev {len(minimal)} hållplatser till {OUTPUT} ({OUTPUT.stat().st_size} byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
