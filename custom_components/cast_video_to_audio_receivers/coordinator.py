"""Bridge coordinator tying zones, relays, receiver daemons and monitor together."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .cast_monitor import CastMonitor
from .const import (
    CONF_AUDIO_BITRATE,
    CONF_CERT_MANIFEST,
    CONF_ENABLE_MONITOR,
    CONF_FFMPEG_PATH,
    CONF_FRIENDLY_NAME,
    CONF_MONITOR_VIDEO_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_TLS_PORT,
    CONF_ZONE_ID,
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_FFMPEG_PATH,
    DEFAULT_TLS_PORT,
    DOMAIN,
)
from .daemon_manager import ReceiverDaemonManager
from .relay import AudioRelayManager, ZoneRelay

_LOGGER = logging.getLogger(__name__)


class CastVideoAudioBridge:
    """Main integration bridge."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        self.hass = hass
        self.entry_id = entry_data["entry_id"]
        self.zones: dict[str, dict[str, Any]] = entry_data["zones"]
        self.relays: dict[str, ZoneRelay] = {}
        self._ffmpeg_path = entry_data.get(CONF_FFMPEG_PATH, DEFAULT_FFMPEG_PATH)
        self._audio_bitrate = entry_data.get(CONF_AUDIO_BITRATE, DEFAULT_AUDIO_BITRATE)

        integration_path = Path(__file__).parent
        storage = Path(hass.config.path("cvta_storage"))
        storage.mkdir(parents=True, exist_ok=True)

        self.relay_manager = AudioRelayManager(
            hass,
            storage,
            ffmpeg_path=self._ffmpeg_path,
            audio_bitrate=self._audio_bitrate,
        )
        self.daemon_manager = ReceiverDaemonManager(hass, integration_path)
        self.monitor = CastMonitor(hass, self)

    async def async_setup(self) -> None:
        """Initialize relays, daemons and monitor."""
        await self.relay_manager.async_init()

        for zone_id, cfg in self.zones.items():
            self.relays[zone_id] = self.relay_manager.create_relay(
                zone_id, cfg[CONF_TARGET_ENTITY]
            )
            await self.daemon_manager.start_zone(zone_id, cfg)

        self.monitor.async_setup()

    async def async_shutdown(self) -> None:
        """Stop everything."""
        await self.monitor.async_shutdown()
        for zone_id in list(self.relays):
            await self.stop_relay(zone_id)
        await self.daemon_manager.async_shutdown()
        await self.relay_manager.async_shutdown()

    async def start_relay(
        self,
        zone_id: str,
        *,
        content_id: str,
        content_type: str | None = None,
        custom_data: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> None:
        """Start or restart relay for zone."""
        relay = self.relays.get(zone_id)
        if not relay:
            raise KeyError(f"Unknown zone: {zone_id}")

        await self.relay_manager.play(
            relay,
            content_id=content_id,
            content_type=content_type,
            custom_data=custom_data,
            title=title,
        )

    async def stop_relay(self, zone_id: str) -> None:
        """Stop relay for zone."""
        relay = self.relays.get(zone_id)
        if relay:
            await self.relay_manager.stop(relay)

    async def stop_all(self) -> None:
        """Stop all active relays."""
        for zone_id in list(self.relays):
            await self.stop_relay(zone_id)


def build_entry_data(hass: HomeAssistant, entry) -> dict[str, Any]:
    """Build runtime data from config entry."""
    zones = entry.data.get("zones", {})
    options = entry.options
    return {
        "entry_id": entry.entry_id,
        "zones": zones,
        CONF_FFMPEG_PATH: options.get(CONF_FFMPEG_PATH, DEFAULT_FFMPEG_PATH),
        CONF_AUDIO_BITRATE: options.get(CONF_AUDIO_BITRATE, DEFAULT_AUDIO_BITRATE),
    }
