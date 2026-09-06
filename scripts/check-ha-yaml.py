#!/usr/bin/env python3
"""
Statiska HA YAML-kontroller före deploy.

Fångar fel som YAML-syntax och HA config_check missar, t.ex.:
- from + not_from / to + not_to i samma state-trigger
- duplicerade automation-/script-id

Utökas via scripts/lib/ha_yaml_checks.py (CHECKS-register).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.ha_yaml_checks import DEFAULT_FILES, run_checks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Statiska HA YAML-kontroller")
    parser.add_argument(
        "paths",
        nargs="*",
        help="YAML-filer (standard: automations.yaml scripts.yaml i projektroten)",
    )
    parser.add_argument(
        "--check",
        choices=sorted(__import__("lib.ha_yaml_checks", fromlist=["CHECKS"]).CHECKS),
        action="append",
        dest="checks",
        help="Kör endast angivna kontroller (kan anges flera gånger)",
    )
    args = parser.parse_args()

    root = SCRIPT_DIR.parent
    if args.paths:
        paths = [Path(p) if Path(p).is_absolute() else root / p for p in args.paths]
    else:
        paths = [root / name for name in DEFAULT_FILES]

    issues = run_checks(paths, args.checks)
    if not issues:
        print(f"OK — inga HA YAML-problem i {len(paths)} fil(er)")
        return 0

    for issue in issues:
        print(issue.format(), file=sys.stderr)
    print(f"\n{len(issues)} problem hittade", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
