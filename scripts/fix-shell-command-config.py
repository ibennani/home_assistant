#!/usr/bin/env python3
"""Återställ shell_command i configuration.yaml från git och behåll seerr."""
from __future__ import annotations

import subprocess
from pathlib import Path

CONFIG = Path("/config/configuration.yaml")
SEERR_BLOCK = """  seerr_process_request: >-
    python3 /config/custom_scripts/seerr_request_notify.py
    --media-type "{{ media_type }}" --title "{{ title }}"
    --tmdb-id "{{ tmdb_id }}" --tvdb-id "{{ tvdb_id }}"
"""
NEEDLE = (
    "  elpris_synka_tibber_faktiska: "
    "python3 /config/scripts/elpris-synka-tibber-faktiska.py\n"
)


def main() -> int:
    subprocess.run(
        ["git", "-C", "/config", "fetch", "origin", "main"],
        check=False,
    )
    base = subprocess.check_output(
        ["git", "-C", "/config", "show", "origin/main:configuration.yaml"],
        text=True,
    )
    if "seerr_process_request" not in base and NEEDLE in base:
        base = base.replace(NEEDLE, NEEDLE + SEERR_BLOCK, 1)
    CONFIG.write_text(base)
    inc = Path("/config/includes/shell_command.yaml")
    if inc.exists():
        inc.unlink()
    print("OK shell_command keys:", _count_keys(base))
    return 0


def _count_keys(text: str) -> int:
    in_block = False
    count = 0
    for line in text.splitlines():
        if line.strip() == "shell_command:":
            in_block = True
            continue
        if in_block:
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            if line.startswith("  ") and ":" in line and not line.strip().startswith("#"):
                count += 1
    return count


if __name__ == "__main__":
    raise SystemExit(main())
