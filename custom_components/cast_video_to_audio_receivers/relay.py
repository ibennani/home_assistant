"""Audio relay from video stream URL to physical Cast audio device."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .const import STREAM_URL_PREFIX
from .ffmpeg_stream import FFmpegStream
from .source.svt_play import resolve_content

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZoneRelay:
    """Active relay state for one zone."""

    zone_id: str
    target_entity: str
    ffmpeg: FFmpegStream
    is_playing: bool = False
    title: str | None = None


class AudioRelayManager:
    """Coordinate ffmpeg transcoding and casting to target speakers."""

    def __init__(
        self,
        hass: HomeAssistant,
        storage_path: Path,
        ffmpeg_path: str,
        audio_bitrate: str,
    ) -> None:
        self._hass = hass
        self._storage_path = storage_path
        self._ffmpeg_path = ffmpeg_path
        self._audio_bitrate = audio_bitrate
        self._http_session: aiohttp.ClientSession | None = None

    async def async_init(self) -> None:
        """Create HTTP session for resolvers."""
        self._http_session = aiohttp.ClientSession()

    async def async_shutdown(self) -> None:
        """Cleanup."""
        if self._http_session:
            await self._http_session.close()

    def create_relay(self, zone_id: str, target_entity: str) -> ZoneRelay:
        """Create relay object for a zone."""
        stream_dir = self._storage_path / zone_id
        ffmpeg = FFmpegStream(
            self._hass,
            stream_dir,
            ffmpeg_path=self._ffmpeg_path,
            audio_bitrate=self._audio_bitrate,
        )
        return ZoneRelay(zone_id=zone_id, target_entity=target_entity, ffmpeg=ffmpeg)

    async def play(
        self,
        relay: ZoneRelay,
        content_id: str,
        content_type: str | None = None,
        custom_data: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> None:
        """Resolve content, transcode audio, cast to target entity."""
        if not self._http_session:
            raise RuntimeError("Relay manager not initialized")

        stream_url = await resolve_content(
            self._http_session,
            content_id,
            content_type=content_type,
            custom_data=custom_data,
        )

        _LOGGER.info(
            "Starting audio relay for zone %s -> %s (%s)",
            relay.zone_id,
            relay.target_entity,
            stream_url[:120],
        )

        await relay.ffmpeg.start(stream_url)

        internal_url = self._hass.config.internal_url or self._hass.config.external_url
        if not internal_url:
            raise RuntimeError("Home Assistant internal_url or external_url must be set")

        playlist_url = (
            f"{internal_url.rstrip('/')}{STREAM_URL_PREFIX}/{relay.zone_id}/stream.m3u8"
        )

        await self._hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": relay.target_entity,
                "media_content_type": "music",
                "media_content_id": playlist_url,
                "extra": {"title": title or "Cast video to audio"},
            },
            blocking=True,
        )
        relay.is_playing = True
        relay.title = title

    async def stop(self, relay: ZoneRelay) -> None:
        """Stop relay and physical playback."""
        relay.is_playing = False
        relay.title = None
        await relay.ffmpeg.stop()

        if self._hass.states.get(relay.target_entity):
            await self._hass.services.async_call(
                "media_player",
                "media_stop",
                {"entity_id": relay.target_entity},
                blocking=True,
            )
