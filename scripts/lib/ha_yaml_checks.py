"""Statiska HA YAML-kontroller som syntaxkontroll och config_check inte fångar."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

GUARD_TEMPLATE = (
    "{{ trigger.from_state is not none and trigger.to_state is not none and "
    "trigger.from_state.state not in ['unavailable', 'unknown', 'none'] and "
    "trigger.to_state.state not in ['unavailable', 'unknown', 'none'] }}"
)


@dataclass(frozen=True)
class Issue:
    file: Path
    line: int
    check: str
    message: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: [{self.check}] {self.message}"


def _ha_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


if yaml is not None:
    yaml.SafeLoader.add_multi_constructor("!", _ha_tag)


def is_state_trigger_line(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("- trigger: state") or stripped.startswith("- platform: state")


def parse_trigger_block(lines: list[str], start: int, base_indent: int) -> tuple[list[str], int]:
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
    ci = base_indent + 4
    vi = ci + 2
    return [
        f"{' ' * ci}conditions:\n",
        f"{' ' * ci}- condition: template\n",
        f"{' ' * vi}value_template: >\n",
        f"{' ' * (vi + 2)}{GUARD_TEMPLATE}\n",
    ]


def state_trigger_conflicts(block_lines: list[str]) -> list[str]:
    """Returnera felmeddelanden för ogiltiga from/not_from- eller to/not_to-kombinationer."""
    keys = trigger_keys(block_lines)
    if not (keys.get("trigger") or keys.get("platform")):
        return []

    errors: list[str] = []
    if keys.get("from") and keys.get("not_from"):
        errors.append("kombinera inte `from` med `not_from` i samma state-trigger")
    if keys.get("to") and keys.get("not_to"):
        errors.append("kombinera inte `to` med `not_to` i samma state-trigger")
    return errors


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


def check_state_trigger_conflicts(path: Path) -> list[Issue]:
    if not path.is_file():
        return []

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    issues: list[Issue] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_state_trigger_line(line):
            base_indent = len(line) - len(line.lstrip())
            block_lines, end = parse_trigger_block(lines, i, base_indent)
            for msg in state_trigger_conflicts(block_lines):
                issues.append(
                    Issue(
                        file=path,
                        line=i + 1,
                        check="state_trigger_conflict",
                        message=msg,
                    )
                )
            i = end
            continue
        i += 1
    return issues


def check_duplicate_ids(path: Path, label: str) -> list[Issue]:
    if not path.is_file():
        return []

    text = path.read_text(encoding="utf-8")
    id_lines: dict[str, list[int]] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = re.match(r"^(?:-\s+id:|  id:)\s*(.+?)\s*$", line)
        if not match:
            continue
        raw = match.group(1).strip()
        if raw and raw[0] in "'\"":
            raw = raw[1:-1]
        id_lines.setdefault(raw, []).append(lineno)

    issues: list[Issue] = []
    for item_id, lines in id_lines.items():
        if len(lines) > 1:
            issues.append(
                Issue(
                    file=path,
                    line=lines[0],
                    check="duplicate_id",
                    message=f"duplicerat {label}-id `{item_id}` (även rad {', '.join(str(n) for n in lines[1:])})",
                )
            )
    return issues


def check_legacy_trigger_platform(path: Path) -> list[Issue]:
    """Varning: `platform: state` i triggers-lista (äldre syntax, ofta oavsiktlig)."""
    if not path.is_file():
        return []

    issues: list[Issue] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if re.search(r"^\s+-\s+platform:\s+state\b", line):
            issues.append(
                Issue(
                    file=path,
                    line=lineno,
                    check="legacy_trigger_syntax",
                    message="använd `trigger: state` i triggers-listan, inte `platform: state`",
                )
            )
    return issues


CHECKS: dict[str, Callable[[Path], list[Issue]]] = {
    "state_trigger_conflicts": check_state_trigger_conflicts,
    "duplicate_automation_ids": lambda p: check_duplicate_ids(p, "automation")
    if p.name == "automations.yaml"
    else [],
    "duplicate_script_ids": lambda p: check_duplicate_ids(p, "script")
    if p.name == "scripts.yaml"
    else [],
    "legacy_trigger_syntax": check_legacy_trigger_platform,
}


DEFAULT_FILES = ("automations.yaml", "scripts.yaml")


def run_checks(paths: Iterable[Path], checks: Iterable[str] | None = None) -> list[Issue]:
    selected = list(checks) if checks else list(CHECKS)
    issues: list[Issue] = []
    for path in paths:
        for name in selected:
            fn = CHECKS.get(name)
            if fn is None:
                continue
            issues.extend(fn(path))
    return issues


def fix_state_triggers_in_file(path: Path, dry_run: bool = False) -> dict[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    stats = {"triggers_fixed": 0, "automations_touched": 0}
    automation_touched = False

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("alias:") or stripped.startswith("- alias:"):
            if automation_touched:
                stats["automations_touched"] += 1
            automation_touched = False

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
