"""Cast video to audio receivers integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CastVideoAudioBridge, build_entry_data
from .ipc_server import register_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration."""
    register_views(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    bridge = CastVideoAudioBridge(hass, build_entry_data(hass, entry))
    await bridge.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = bridge

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    bridge: CastVideoAudioBridge | None = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if bridge:
        await bridge.async_shutdown()
    return True
