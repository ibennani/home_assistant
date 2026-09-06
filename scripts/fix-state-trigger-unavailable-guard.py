#!/usr/bin/env python3
"""
Fix state triggers where not_from/not_to conflict with from/to (HA validation error).

Strategy:
- Remove not_from when `from` is present; remove not_to when `to` is present.
- If both `from` and `to` remain, no extra guard (unavailable transitions don't match).
- Otherwise keep surviving not_from/not_to, or add trigger-level template condition.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.ha_yaml_checks import fix_state_triggers_in_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix not_from/not_to trigger conflicts")
    parser.add_argument(
        "path",
        nargs="?",
        default="automations.yaml",
        help="Path to automations.yaml",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write")
    args = parser.parse_args()
    path = Path(args.path)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return 1
    stats = fix_state_triggers_in_file(path, dry_run=args.dry_run)
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"Fixed {stats['triggers_fixed']} triggers across ~{stats['automations_touched']} automations in {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
