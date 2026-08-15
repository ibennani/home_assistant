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
import copy
import sys
from pathlib import Path

GUARD_TEMPLATE = (
    "{{ trigger.from_state is not none and trigger.to_state is not none and "
    "trigger.from_state.state not in ['unavailable', 'unknown', 'none'] and "
    "trigger.to_state.state not in ['unavailable', 'unknown', 'none'] }}"
)

GUARD_CONDITION = {
    "condition": "template",
    "value_template": GUARD_TEMPLATE,
}


def is_state_trigger_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("- trigger: state") or stripped.startswith("- platform: state")


def parse_trigger_block(lines: list[str], start: int, base_indent: int) -> tuple[dict, int]:
    """Parse one trigger list item starting at `start` (the `- trigger:` line)."""
    block_lines = [lines[start]]
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and line.lstrip().startswith("- "):
            break
        block_lines.append(line)
        i += 1
    return block_lines, i


def trigger_keys(block_lines: list[str]) -> dict[str, bool]:
    keys: dict[str, bool] = {}
    for line in block_lines:
        stripped = line.strip()
        if stripped.startswith("- trigger: state") or stripped.startswith("- platform: state"):
            keys["trigger"] = True
        for key in ("from", "to", "not_from", "not_to", "for", "entity_id"):
            if stripped.startswith(f"{key}:"):
                keys[key] = True
    return keys


def has_guard_condition(block_lines: list[str]) -> bool:
    in_conditions = False
    for line in block_lines:
        stripped = line.strip()
        if stripped.startswith("conditions:"):
            in_conditions = True
            continue
        if in_conditions and "unavailable" in stripped and "value_template" in stripped:
            return True
    return False


def remove_key_block(block_lines: list[str], key: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(block_lines):
        line = block_lines[i]
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            key_indent = len(line) - len(line.lstrip())
            i += 1
            while i < len(block_lines):
                nxt = block_lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                nindent = len(nxt) - len(nxt.lstrip())
                nstripped = nxt.strip()
                if nindent < key_indent:
                    break
                if nindent == key_indent and not nstripped.startswith("- "):
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return out


def format_condition_lines(base_indent: int) -> list[str]:
    """Indent conditions under trigger (base_indent + 4)."""
    ci = base_indent + 4
    vi = ci + 2
    return [
        f"{' ' * ci}conditions:\n",
        f"{' ' * ci}- condition: template\n",
        f"{' ' * vi}value_template: >\n",
        f"{' ' * (vi + 2)}{GUARD_TEMPLATE}\n",
    ]


def fix_trigger_block(block_lines: list[str]) -> tuple[list[str], bool]:
    if not block_lines:
        return block_lines, False

    base_indent = len(block_lines[0]) - len(block_lines[0].lstrip())
    keys = trigger_keys(block_lines)
    if not (keys.get("trigger") or keys.get("platform")):
        return block_lines, False

    has_from = keys.get("from", False)
    has_to = keys.get("to", False)
    had_not_from = keys.get("not_from", False)
    had_not_to = keys.get("not_to", False)

    removed_not_from = False
    removed_not_to = False
    new_lines = copy.deepcopy(block_lines)

    if has_from and had_not_from:
        new_lines = remove_key_block(new_lines, "not_from")
        removed_not_from = True
        had_not_from = False

    if has_to and had_not_to:
        new_lines = remove_key_block(new_lines, "not_to")
        removed_not_to = True
        had_not_to = False

    if not removed_not_from and not removed_not_to:
        return block_lines, False

    keys_after = trigger_keys(new_lines)
    need_guard = False
    if keys_after.get("from") and keys_after.get("to"):
        need_guard = False
    elif keys_after.get("not_from") or keys_after.get("not_to"):
        need_guard = False
    else:
        need_guard = True

    if need_guard and not has_guard_condition(new_lines):
        new_lines = new_lines + format_condition_lines(base_indent)

    return new_lines, True


def process_file(path: Path, dry_run: bool = False) -> dict[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    stats = {"triggers_fixed": 0, "automations_touched": 0}
    current_alias = None
    automation_touched = False

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if "alias:" in stripped and stripped.startswith("alias:"):
            if automation_touched:
                stats["automations_touched"] += 1
            automation_touched = False
            current_alias = stripped.split("alias:", 1)[1].strip().strip("'\"")
        elif stripped.startswith("- alias:"):
            if automation_touched:
                stats["automations_touched"] += 1
            automation_touched = False
            current_alias = stripped.split("- alias:", 1)[1].strip().strip("'\"")

        if is_state_trigger_line(line):
            base_indent = len(line) - len(line.lstrip())
            block_lines, end = parse_trigger_block(lines, i, base_indent)
            fixed, changed = fix_trigger_block(block_lines)
            if changed:
                stats["triggers_fixed"] += 1
                automation_touched = True
                out.extend(fixed)
                i = end
                continue

        out.append(line)
        i += 1

    if automation_touched:
        stats["automations_touched"] += 1

    if not dry_run and stats["triggers_fixed"] > 0:
        path.write_text("".join(out), encoding="utf-8")

    return stats


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
    stats = process_file(path, dry_run=args.dry_run)
    print(
        f"{'[dry-run] ' if args.dry_run else ''}"
        f"Fixed {stats['triggers_fixed']} triggers across ~{stats['automations_touched']} automations in {path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
