#!/usr/bin/env python3
"""
Granska HA YAML och rapportera potentiella problem — ändrar inget.

Kör: python3 scripts/audit-ha-yaml.py [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.ha_yaml_checks import DEFAULT_FILES, Issue, run_checks  # noqa: E402

ROOT = SCRIPT_DIR.parent
VALID_CONDITIONS = {
    "and",
    "device",
    "not",
    "numeric_state",
    "or",
    "state",
    "sun",
    "template",
    "time",
    "trigger",
    "zone",
}


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    check: str
    severity: str  # error | warning | info
    message: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: [{self.severity}/{self.check}] {self.message}"


def _issue_to_finding(issue: Issue, severity: str = "error") -> Finding:
    return Finding(
        file=str(issue.file),
        line=issue.line,
        check=issue.check,
        severity=severity,
        message=issue.message,
    )


def load_script_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.is_file():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z][a-z0-9_]+):\s*$", line)
        if m:
            ids.add(m.group(1))
    return ids


def check_script_references(automations_path: Path, scripts_path: Path) -> list[Finding]:
    """Flagga entity_id script.* som saknas i scripts.yaml (inte service-anrop script.turn_on)."""
    if not automations_path.is_file():
        return []
    script_ids = load_script_ids(scripts_path)
    findings: list[Finding] = []
    entity_pattern = re.compile(r"^\s*entity_id:\s*script\.([a-z0-9_]+)\s*$")
    list_pattern = re.compile(r"^\s*-\s*script\.([a-z0-9_]+)\s*$")
    in_entity_list = False
    list_indent = 0

    for lineno, line in enumerate(automations_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        m = entity_pattern.match(line)
        if m:
            sid = m.group(1)
            if sid not in script_ids:
                findings.append(
                    Finding(
                        file=str(automations_path),
                        line=lineno,
                        check="missing_script",
                        severity="warning",
                        message=f"entity_id script.{sid} saknas i scripts.yaml",
                    )
                )
            in_entity_list = stripped.endswith(":") and "entity_id" in stripped
            if in_entity_list:
                list_indent = indent + 2
            continue

        if in_entity_list:
            if not stripped or indent < list_indent:
                in_entity_list = False
            else:
                m = list_pattern.match(line)
                if m:
                    sid = m.group(1)
                    if sid not in script_ids:
                        findings.append(
                            Finding(
                                file=str(automations_path),
                                line=lineno,
                                check="missing_script",
                                severity="warning",
                                message=f"entity_id script.{sid} saknas i scripts.yaml",
                            )
                        )
    return findings


def check_choose_as_condition(path: Path) -> list[Finding]:
    """`- choose:` direkt under `conditions:` är ogiltigt (choose är action, inte condition)."""
    if not path.is_file():
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[Finding] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^(\s*)conditions:\s*$", line):
            cond_indent = len(line) - len(line.lstrip())
            item_indent = cond_indent + 2
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    j += 1
                    continue
                nindent = len(nxt) - len(nxt.lstrip())
                if nindent <= cond_indent:
                    break
                stripped = nxt.strip()
                if nindent == item_indent and stripped.startswith("- choose:"):
                    findings.append(
                        Finding(
                            file=str(path),
                            line=j + 1,
                            check="choose_as_condition",
                            severity="error",
                            message="`choose` är inte en giltig condition — använd `condition:` + `sequence:`",
                        )
                    )
                if nindent == item_indent and stripped.startswith("- condition:"):
                    cond_type = stripped.split(":", 1)[1].strip()
                    if cond_type and cond_type not in VALID_CONDITIONS:
                        findings.append(
                            Finding(
                                file=str(path),
                                line=j + 1,
                                check="invalid_condition_type",
                                severity="error",
                                message=f"ogiltig condition-typ `{cond_type}`",
                            )
                        )
                j += 1
            i = j
            continue
        i += 1
    return findings


def check_mixed_action_keys(path: Path) -> list[Finding]:
    """Automation med både `action:` och `actions:` på samma nivå."""
    if not path.is_file() or path.name != "automations.yaml":
        return []

    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[Finding] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("- ") and ("alias:" in lines[i] or lines[i].strip() == "-"):
            start = i
            has_action = False
            has_actions = False
            action_line = 0
            base_indent = 2
            j = i + 1
            while j < len(lines):
                if lines[j].startswith("- ") and j > start + 1:
                    break
                if re.match(r"^  action:\s*$", lines[j]):
                    has_action = True
                    action_line = j + 1
                if re.match(r"^  actions:\s*$", lines[j]):
                    has_actions = True
                j += 1
            if has_action and has_actions:
                findings.append(
                    Finding(
                        file=str(path),
                        line=action_line,
                        check="mixed_action_keys",
                        severity="warning",
                        message="automation har både `action:` och `actions:` — kan ge oväntat beteende",
                    )
                )
            i = j
            continue
        i += 1
    return findings


def audit(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    issues = run_checks(paths)
    findings.extend(_issue_to_finding(i) for i in issues)

    auto = next((p for p in paths if p.name == "automations.yaml"), ROOT / "automations.yaml")
    scripts = ROOT / "scripts.yaml"

    findings.extend(check_script_references(auto, scripts))
    for path in paths:
        if path.name == "automations.yaml":
            findings.extend(check_choose_as_condition(path))
            findings.extend(check_mixed_action_keys(path))

    return sorted(findings, key=lambda f: (f.severity != "error", f.file, f.line, f.check))


def main() -> int:
    parser = argparse.ArgumentParser(description="Granska HA YAML utan att ändra filer")
    parser.add_argument("paths", nargs="*", help="YAML-filer (standard: automations.yaml scripts.yaml)")
    parser.add_argument("--json", action="store_true", help="JSON-utdata")
    parser.add_argument("--severity", choices=["error", "warning", "info"], help="Filtrera minsta severity")
    args = parser.parse_args()

    if args.paths:
        paths = [Path(p) if Path(p).is_absolute() else ROOT / p for p in args.paths]
    else:
        paths = [ROOT / name for name in DEFAULT_FILES]

    findings = audit(paths)
    if args.severity:
        rank = {"info": 0, "warning": 1, "error": 2}
        min_rank = rank[args.severity]
        findings = [f for f in findings if rank.get(f.severity, 0) >= min_rank]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=2))
    else:
        if not findings:
            print(f"OK — inga fynd i {len(paths)} fil(er)")
        else:
            for f in findings:
                print(f.format())
            errors = sum(1 for f in findings if f.severity == "error")
            warnings = sum(1 for f in findings if f.severity == "warning")
            print(f"\n{len(findings)} fynd ({errors} fel, {warnings} varningar)", file=sys.stderr)

    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
