"""Monitor video Cast devices and relay audio in the background."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import STATE_IDLE, STATE_OFF, STATE_PLAYING
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DEFAULT_MEDIA_RECEIVER_APP_ID

_LOGGER = logging.getLogger(__name__)


class CastMonitor:
    """Watch configured video media_players and relay audio automatically."""

    def __init__(self, hass: HomeAssistant, bridge: Any) -> None:
        self._hass = hass
        self._bridge = bridge
        self._unsub: list[Any] = []

    def async_setup(self) -> None:
        """Register state listeners for monitor entities."""
        for zone_id, cfg in self._bridge.zones.items():
            if not cfg.get("enable_monitor"):
                continue
            entity_id = cfg.get("monitor_video_entity")
            if not entity_id:
                continue

            _LOGGER.info(
                "Monitoring %s for zone %s audio relay",
                entity_id,
                zone_id,
            )
            unsub = async_track_state_change_event(
                self._hass,
                [entity_id],
                self._make_callback(zone_id, entity_id),
            )
            self._unsub.append(unsub)

    @callback
    def _make_callback(self, zone_id: str, entity_id: str):
        @callback
        def _state_changed(event: Event) -> None:
            self._hass.async_create_task(
                self._handle_state(zone_id, entity_id, event.data.get("new_state"))
            )

        return _state_changed

    async def _handle_state(
        self, zone_id: str, entity_id: str, new_state: State | None
    ) -> None:
        if not new_state:
            await self._bridge.stop_relay(zone_id)
            return

        if new_state.state in (STATE_OFF, STATE_IDLE):
            await self._bridge.stop_relay(zone_id)
            return

        if new_state.state != STATE_PLAYING:
            return

        attrs = new_state.attributes
        content_id = attrs.get("media_content_id")
        content_type = attrs.get("media_content_type")
        app_id = attrs.get("app_id")
        app_name = (attrs.get("app_name") or "").lower()

        if not content_id:
            return

        # Default media receiver exposes direct URLs
        if app_id == DEFAULT_MEDIA_RECEIVER_APP_ID and str(content_id).startswith(
            ("http://", "https://")
        ):
            await self._bridge.start_relay(
                zone_id,
                content_id=str(content_id),
                content_type=content_type,
                title=attrs.get("media_title"),
            )
            return

        # SVT Play on Chromecast — try channel slug in content_id or title heuristics
        if "svt" in app_name or "svt" in str(content_id).lower():
            custom_data: dict[str, Any] = {}
            lowered = str(content_id).lower()
            for channel in ("svt1", "svt2", "svt24", "barnkanalen", "kunskapskanalen"):
                if channel in lowered:
                    custom_data["channel"] = channel
                    break

            try:
                await self._bridge.start_relay(
                    zone_id,
                    content_id=str(content_id),
                    content_type=content_type,
                    custom_data=custom_data,
                    title=attrs.get("media_title"),
                )
            except Exception as err:
                _LOGGER.debug(
                    "Could not relay monitor cast from %s: %s", entity_id, err
                )

    async def async_shutdown(self) -> None:
        """Remove listeners."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
