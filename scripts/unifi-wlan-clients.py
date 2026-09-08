#!/usr/bin/env python3
"""Hämtar aktiva UniFi-klienter med SSID (essid) från Network Controller API.

Läser unifi_* från /config/secrets.yaml, eller faller tillbaka till
UniFi-integrationens config entry i .storage/core.config_entries.

Användning:
  python3 unifi-wlan-clients.py
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PLACEHOLDER_VALUES = {"", "BYT_UT", "byt_ut"}
LAST_PATH = Path("/config/www/unifi-wlan-last.json")
DEBUG_PATH = Path("/config/www/unifi-wlan-debug.txt")


def load_secrets() -> dict[str, str]:
    path = Path("/config/secrets.yaml")
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-zA-Z0-9_]+)\s*:\s*(.+?)\s*$", line.strip())
        if not match:
            continue
        key, raw = match.group(1), match.group(2)
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        elif raw.startswith("'") and raw.endswith("'"):
            raw = raw[1:-1]
        values[key] = raw
    return values


def load_unifi_from_config_entry() -> dict[str, str]:
    """Läser UniFi-uppgifter från HA:s config entry (samma som integrationen)."""
    path = Path("/config/.storage/core.config_entries")
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    for entry in payload.get("data", {}).get("entries", []):
        if entry.get("domain") != "unifi":
            continue
        data = entry.get("data") or {}
        host = str(data.get("host") or "").strip()
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "").strip()
        if not host or not username or not password:
            continue
        port = data.get("port", 443)
        verify_ssl = data.get("verify_ssl", False)
        return {
            "unifi_host": host,
            "unifi_username": username,
            "unifi_password": password,
            "unifi_site": str(data.get("site") or "default"),
            "unifi_port": str(port),
            "unifi_verify_ssl": "true" if verify_ssl else "false",
        }
    return {}


def resolve_unifi_config() -> dict[str, str]:
    secrets = load_secrets()
    entry = load_unifi_from_config_entry()
    merged = {**entry, **{k: v for k, v in secrets.items() if k.startswith("unifi_")}}
    for key, value in entry.items():
        current = merged.get(key, "")
        if current in PLACEHOLDER_VALUES or not current:
            merged[key] = value
    return merged


def normalize_mac(mac: str) -> str:
    return mac.strip().lower()


def empty_result() -> dict:
    return {"count": 0, "data": []}


def emit(result: dict) -> None:
    payload = json.dumps(result)
    LAST_PATH.write_text(payload, encoding="utf-8")
    print(payload)


class UniFiSession:
    def __init__(self, host: str, port: int, site: str, verify_ssl: bool) -> None:
        self.host = host
        self.port = port
        self.site = site
        self.verify_ssl = verify_ssl
        self.csrf_token = ""
        self.cookie_jar = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        if not verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        handlers = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]
        if not verify_ssl:
            handlers.append(urllib.request.HTTPSHandler(context=ctx))
        self.opener = urllib.request.build_opener(*handlers)
        self.ctx = ctx

    def base_url(self, unifi_os: bool) -> str:
        scheme = "https"
        if unifi_os:
            return f"{scheme}://{self.host}:{self.port}"
        return f"{scheme}://{self.host}:{self.port or 8443}"

    def request(
        self,
        method: str,
        url: str,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        body = None
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        if data is not None:
            body = json.dumps(data).encode()
            req_headers["Content-Type"] = "application/json"
        if self.csrf_token:
            req_headers["X-CSRF-Token"] = self.csrf_token
        request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
                csrf = response.headers.get("X-CSRF-Token")
                if csrf:
                    self.csrf_token = csrf
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {exc.code} for {url}: {raw[:200]}") from exc

    def login_unifi_os(self, username: str, password: str) -> None:
        base = self.base_url(True)
        payload = self.request(
            "POST",
            f"{base}/api/auth/login",
            {"username": username, "password": password, "remember": True},
        )
        if payload.get("meta", {}).get("rc") == "ok" or self.cookie_jar:
            return
        raise RuntimeError("UniFi OS login failed")

    def login_legacy(self, username: str, password: str) -> None:
        base = self.base_url(False)
        self.request(
            "POST",
            f"{base}/api/login",
            {"username": username, "password": password, "remember": True},
        )

    def discover_site(self, unifi_os: bool) -> str:
        base = self.base_url(unifi_os)
        if unifi_os:
            prefix = f"{base}/proxy/network/api"
        else:
            prefix = f"{base}/api"
        for path in (f"{prefix}/self/sites", f"{prefix}/stat/sites"):
            try:
                payload = self.request("GET", path)
            except (RuntimeError, urllib.error.URLError, json.JSONDecodeError):
                continue
            sites = payload.get("data", [])
            if sites:
                return str(sites[0].get("name") or sites[0].get("desc") or self.site)
        return self.site

    def fetch_stations(self, unifi_os: bool, site: str) -> list[dict]:
        base = self.base_url(unifi_os)
        if unifi_os:
            url = f"{base}/proxy/network/api/s/{site}/stat/sta"
        else:
            url = f"{base}/api/s/{site}/stat/sta"
        payload = self.request("GET", url)
        if payload.get("meta", {}).get("rc") not in (None, "ok"):
            raise RuntimeError(payload.get("meta", {}).get("msg", "stat/sta failed"))
        return payload.get("data", [])


def parse_station(station: dict) -> dict | None:
    mac = normalize_mac(str(station.get("mac") or ""))
    if not mac:
        return None
    essid = str(station.get("essid") or station.get("ssid") or "").strip()
    is_wired = bool(station.get("is_wired"))
    is_guest = bool(station.get("is_guest"))
    hostname = str(
        station.get("hostname")
        or station.get("name")
        or station.get("host_name")
        or ""
    ).strip()
    ip = str(station.get("ip") or station.get("last_ip") or "").strip()
    return {
        "mac": mac,
        "ip": ip,
        "hostname": hostname,
        "essid": essid,
        "is_wired": is_wired,
        "is_guest": is_guest,
    }


def fetch_clients(secrets: dict[str, str]) -> tuple[list[dict], str]:
    host = secrets.get("unifi_host") or secrets.get("edgerouter_host", "192.168.0.1")
    username = secrets.get("unifi_username", "")
    password = secrets.get("unifi_password", "")
    site = secrets.get("unifi_site", "default")
    port_raw = secrets.get("unifi_port", "443")
    verify_ssl = secrets.get("unifi_verify_ssl", "false").lower() in ("1", "true", "yes")

    if username in PLACEHOLDER_VALUES or password in PLACEHOLDER_VALUES:
        raise RuntimeError("missing unifi credentials (secrets.yaml or UniFi integration)")

    try:
        port = int(port_raw)
    except ValueError:
        port = 443

    last_error: Exception | None = None
    for unifi_os in (True, False):
        try:
            session = UniFiSession(host, port if unifi_os else (port or 8443), site, verify_ssl)
            if unifi_os:
                session.login_unifi_os(username, password)
            else:
                session.login_legacy(username, password)
            resolved_site = site if site not in PLACEHOLDER_VALUES else session.discover_site(unifi_os)
            stations = session.fetch_stations(unifi_os, resolved_site)
            clients = [parsed for parsed in (parse_station(s) for s in stations) if parsed]
            clients.sort(key=lambda item: (item.get("hostname") or item["mac"]).lower())
            mode = "unifi_os" if unifi_os else "legacy"
            return clients, f"{mode} host={host} site={resolved_site}"
        except Exception as exc:
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise RuntimeError("UniFi login failed")


def main() -> None:
    try:
        secrets = resolve_unifi_config()
        clients, info = fetch_clients(secrets)
        result = {"count": len(clients), "data": clients}
        DEBUG_PATH.write_text(f"ok {info} clients={len(clients)}\n", encoding="utf-8")
        emit(result)
    except Exception as exc:
        DEBUG_PATH.write_text(f"error: {exc!r}\n", encoding="utf-8")
        emit(empty_result())


if __name__ == "__main__":
    main()
