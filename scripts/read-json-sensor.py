#!/usr/bin/env python3
"""Läser en JSON-fil och skriver den till stdout för command_line-sensorer."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    empty = {"count": 0, "data": []}
    if path is None or not path.exists():
        print(json.dumps(empty))
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps(empty))
        return
    if not isinstance(payload, dict):
        print(json.dumps(empty))
        return
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
