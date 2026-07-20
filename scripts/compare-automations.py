#!/usr/bin/env python3
"""Jämför två automations.yaml-filer per id/alias."""
import argparse
import hashlib
import re
import sys
from pathlib import Path


def split_automations(text: str) -> dict[str, dict]:
    """Dela yaml i automation-block indexerade på id eller alias."""
    blocks: dict[str, dict] = {}
    current_lines: list[str] = []
    current_key: str | None = None
    current_alias: str | None = None

    def flush():
        nonlocal current_lines, current_key, current_alias
        if not current_lines:
            return
        body = "\n".join(current_lines)
        key = current_key or current_alias or f"__anon_{len(blocks)}"
        blocks[key] = {
            "id": current_key,
            "alias": current_alias,
            "body": body,
            "hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        }
        current_lines = []
        current_key = None
        current_alias = None

    for line in text.splitlines():
        if line.startswith("- ") and current_lines:
            flush()
        if line.startswith("- alias:") or line.startswith("  alias:"):
            current_alias = line.split("alias:", 1)[1].strip().strip('"').strip("'")
        m = re.match(r"^  id: ['\"]?([^'\"]+)", line)
        if m:
            current_key = m.group(1)
        if line.startswith("- ") or current_lines:
            current_lines.append(line)
    flush()
    return blocks


def compare(left: dict[str, dict], right: dict[str, dict], left_label: str, right_label: str) -> int:
    left_keys = set(left)
    right_keys = set(right)

    added = sorted(right_keys - left_keys)
    removed = sorted(left_keys - right_keys)
    common = sorted(left_keys & right_keys)

    changed = [k for k in common if left[k]["hash"] != right[k]["hash"]]

    print(f"{left_label}: {len(left)} automationer")
    print(f"{right_label}: {len(right)} automationer")
    print()
    print(f"TILLAGDA i {right_label} ({len(added)}):")
    for k in added:
        a = right[k]
        print(f"  + [{a.get('id') or k}] {a.get('alias', '?')}")
    print()
    print(f"BORTTAGNA från {right_label} ({len(removed)}):")
    for k in removed:
        a = left[k]
        print(f"  - [{a.get('id') or k}] {a.get('alias', '?')}")
    print()
    print(f"ÄNDRADE innehåll ({len(changed)}):")
    for k in changed:
        print(f"  ~ [{left[k].get('id') or k}] {left[k].get('alias', '?')}")

    return len(added) + len(removed) + len(changed)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jämför två automations.yaml-filer (t.ex. backup vs nuvarande)."
    )
    parser.add_argument("baseline", type=Path, help="Referensfil (t.ex. backup)")
    parser.add_argument("current", type=Path, help="Fil att jämföra mot referensen")
    parser.add_argument("--baseline-label", default="Baseline")
    parser.add_argument("--current-label", default="Nuvarande")
    args = parser.parse_args()

    for path in (args.baseline, args.current):
        if not path.is_file():
            print(f"Fil saknas: {path}", file=sys.stderr)
            return 1

    baseline = split_automations(args.baseline.read_text(encoding="utf-8"))
    current = split_automations(args.current.read_text(encoding="utf-8"))
    diff_count = compare(baseline, current, args.baseline_label, args.current_label)
    return 1 if diff_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
