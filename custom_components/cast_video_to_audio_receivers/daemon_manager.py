"""Manage the Node.js cast receiver subprocess per zone."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DEFAULT_TLS_PORT

_LOGGER = logging.getLogger(__name__)


class ReceiverDaemonManager:
    """Start and supervise cast receiver daemons."""

    def __init__(self, hass: HomeAssistant, integration_path: Path) -> None:
        self._hass = hass
        self._integration_path = integration_path
        self._receiver_dir = integration_path / "receiver"
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    def _node_binary(self) -> str:
        return shutil.which("node") or "node"

    def _receiver_entry(self) -> Path:
        entry = self._receiver_dir / "src" / "index.js"
        if not entry.exists():
            raise HomeAssistantError(
                "Cast receiver files not found. Reinstall the integration."
            )
        return entry

    def _receiver_cwd(self, entry: Path) -> Path:
        return entry.parent.parent

    async def start_zone(self, zone_id: str, config: dict[str, Any]) -> None:
        """Start receiver daemon for a zone."""
        await self.stop_zone(zone_id)

        cert_manifest = config.get("cert_manifest")
        if not cert_manifest or not Path(cert_manifest).exists():
            _LOGGER.warning(
                "Zone %s: cert manifest missing (%s) — virtual receiver not started",
                zone_id,
                cert_manifest,
            )
            return

        entry = self._receiver_entry()
        cwd = self._receiver_cwd(entry)

        internal_url = self._hass.config.internal_url or "http://127.0.0.1:8123"
        tls_port = config.get("tls_port", DEFAULT_TLS_PORT + hash(zone_id) % 100)

        env = {
            **os.environ,
            "CVAR_ZONE_ID": zone_id,
            "CVAR_FRIENDLY_NAME": config["friendly_name"],
            "CVAR_CERT_MANIFEST": cert_manifest,
            "CVAR_TLS_PORT": str(tls_port),
            "CVAR_HA_URL": internal_url.rstrip("/"),
        }

        cmd = [self._node_binary(), str(entry)]
        _LOGGER.info(
            "Starting cast receiver for zone %s (%s) on port %s",
            zone_id,
            config["friendly_name"],
            tls_port,
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[zone_id] = process
        self._hass.async_create_task(self._log_output(zone_id, process))

    async def _log_output(
        self, zone_id: str, process: asyncio.subprocess.Process
    ) -> None:
        """Log receiver stdout/stderr."""
        assert process.stdout and process.stderr

        async def drain(stream: asyncio.StreamReader, level: int) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if text:
                    _LOGGER.log(level, "[%s] %s", zone_id, text)

        await asyncio.gather(
            drain(process.stdout, logging.INFO),
            drain(process.stderr, logging.WARNING),
        )
        code = await process.wait()
        _LOGGER.warning("Cast receiver for zone %s exited with code %s", zone_id, code)

    async def stop_zone(self, zone_id: str) -> None:
        """Stop receiver daemon for a zone."""
        process = self._processes.pop(zone_id, None)
        if not process or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    async def async_shutdown(self) -> None:
        """Stop all receiver processes."""
        for zone_id in list(self._processes):
            await self.stop_zone(zone_id)
