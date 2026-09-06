#!/usr/bin/env python3
"""
Post-deploy-kontroller mot live Home Assistant (REST).

Fångar fel som offline-lint och config_check missar, t.ex.:
- automation.* i state unavailable (trasig trigger/setup)
- aktiva repairs med severity error (via WebSocket)

Kräver HA_URL + HA_TOKEN i .env eller miljö.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()}
    dotenv = ROOT / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def ha_request(env: dict[str, str], method: str, path: str, data: dict | None = None) -> object:
    url = env["HA_URL"].rstrip("/") + path
    body = None
    headers = {
        "Authorization": f"Bearer {env['HA_TOKEN']}",
        "Content-Type": "application/json",
    }
    if data is not None:
        body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def check_config(env: dict[str, str]) -> list[str]:
    result = ha_request(env, "POST", "/api/config/core/check_config", {})
    if result.get("result") == "valid":
        return []
    return [f"config_check: {result}"]


def check_unavailable_automations(env: dict[str, str]) -> list[str]:
    states = ha_request(env, "GET", "/api/states")
    issues: list[str] = []
    for st in states:
        eid = st.get("entity_id", "")
        if not eid.startswith("automation."):
            continue
        if st.get("state") == "unavailable":
            name = st.get("attributes", {}).get("friendly_name", eid)
            issues.append(f"unavailable_automation: {eid} ({name})")
    return issues


def check_repairs_ws(env: dict[str, str], min_severity: str) -> list[str]:
    """Hämta repairs via HA WebSocket (stdlib)."""
    import base64
    import hashlib
    import socket
    from urllib.parse import urlparse

    url = env["HA_URL"].rstrip("/")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 8123)
    path = "/api/websocket"
    token = env["HA_TOKEN"]

    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode()

    severity_rank = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}
    min_rank = severity_rank.get(min_severity, 3)

    sock = socket.create_connection((host, port), timeout=30)
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)

    sock.sendall(handshake)
    resp = b""
    while b"\r\n\r\n" not in resp:
        resp += sock.recv(4096)
    if b"101" not in resp.split(b"\r\n", 1)[0]:
        sock.close()
        return [f"repairs_ws: handshake misslyckades ({resp[:120]!r})"]

    def ws_send(msg: dict) -> None:
        payload = json.dumps(msg).encode()
        frame = bytearray([0x81])
        length = len(payload)
        if length < 126:
            frame.append(length | 0x80)
        else:
            frame.append(126 | 0x80)
            frame.extend(length.to_bytes(2, "big"))
        mask = os.urandom(4)
        frame.extend(mask)
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        sock.sendall(frame)

    def ws_recv() -> dict:
        header = sock.recv(2)
        if not header:
            raise OSError("websocket stängd")
        length = header[1] & 0x7F
        if length == 126:
            length = int.from_bytes(sock.recv(2), "big")
        elif length == 127:
            length = int.from_bytes(sock.recv(8), "big")
        if header[1] & 0x80:
            sock.recv(4)  # mask
        data = b""
        while len(data) < length:
            data += sock.recv(length - len(data))
        return json.loads(data.decode())

    issues: list[str] = []
    try:
        msg = ws_recv()
        if msg.get("type") != "auth_required":
            return [f"repairs_ws: oväntat meddelande {msg}"]

        ws_send({"type": "auth", "access_token": token})
        auth = ws_recv()
        if auth.get("type") != "auth_ok":
            return [f"repairs_ws: auth misslyckades {auth}"]

        ws_send({"id": 1, "type": "repairs/list_issues"})
        while True:
            msg = ws_recv()
            if msg.get("id") == 1:
                if not msg.get("success"):
                    return [f"repairs_ws: list_issues misslyckades {msg}"]
                for issue in msg.get("result", {}).get("issues", []):
                    if issue.get("dismissed_version") is not None:
                        continue
                    sev = issue.get("severity", "warning")
                    if severity_rank.get(sev, 0) < min_rank:
                        continue
                    domain = issue.get("domain", "?")
                    iid = issue.get("issue_id", "?")
                    issues.append(f"repair_{sev}: [{domain}] {iid}")
                break
    finally:
        sock.close()
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deploy HA-kontroller (REST + WebSocket)")
    parser.add_argument(
        "--min-repair-severity",
        default="error",
        choices=["debug", "info", "warning", "error", "critical"],
        help="Minsta severity för repairs (default: error)",
    )
    parser.add_argument(
        "--skip-repairs",
        action="store_true",
        help="Hoppa över WebSocket repairs (snabbare)",
    )
    args = parser.parse_args()

    env = load_env()
    if not env.get("HA_URL") or not env.get("HA_TOKEN"):
        print("SKIP: HA_URL/HA_TOKEN saknas", file=sys.stderr)
        return 0

    all_issues: list[str] = []
    try:
        all_issues.extend(check_config(env))
        all_issues.extend(check_unavailable_automations(env))
        if not args.skip_repairs:
            all_issues.extend(check_repairs_ws(env, args.min_repair_severity))
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"FAIL: kunde inte nå Home Assistant — {exc}", file=sys.stderr)
        return 1

    if not all_issues:
        print("OK — inga post-deploy-problem")
        return 0

    for issue in all_issues:
        print(issue, file=sys.stderr)
    print(f"\n{len(all_issues)} post-deploy-problem", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
