#!/usr/bin/env python3
"""Tilldela Z-Wave-stickan (ttyUSB1/FTDI) till Z-Wave JS UI via Supervisor addons.json."""
import json
import os
import sys

SLUG = "a0d7b954_zwavejs2mqtt"
# RFXCOM = ttyUSB0, Z-Wave FTDI = ttyUSB1 (verifierat via SSH /dev/serial/by-id)
DEVICE = "/dev/ttyUSB1"
DEVICE_BY_ID = "/dev/serial/by-id/usb-FTDI_FT230X_Basic_UART_DM00ZRYW-if00-port0"

paths = [
    "/mnt/data/supervisor/addons.json",
    "/data/addons.json",
]
path = next((p for p in paths if os.path.isfile(p)), None)
if not path:
    print("ERROR: addons.json not found", file=sys.stderr)
    sys.exit(1)

with open(path, encoding="utf-8") as f:
    data = json.load(f)

user = data.setdefault("user", {})
entry = user.setdefault(SLUG, {})
dev = DEVICE_BY_ID if os.path.exists(DEVICE_BY_ID) else DEVICE
entry["devices"] = [dev]
entry["boot"] = "auto"

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"PATCHED {path}: devices={entry['devices']}")
