"""HTTP handlers for HLS stream files and IPC from the cast receiver daemon."""

from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, IPC_HEALTH_PATH, IPC_PLAY_PATH, IPC_STOP_PATH, STREAM_URL_PREFIX

_LOGGER = logging.getLogger(__name__)


def _get_bridge_for_zone(hass: HomeAssistant, zone_id: str):
    """Find bridge owning a zone."""
    for bridge in hass.data.get(DOMAIN, {}).values():
        if hasattr(bridge, "relays") and zone_id in bridge.relays:
            return bridge
    return None


def _get_any_bridge(hass: HomeAssistant):
    """Return first available bridge."""
    for bridge in hass.data.get(DOMAIN, {}).values():
        if hasattr(bridge, "relays"):
            return bridge
    return None


class StreamPlaylistView(HomeAssistantView):
    """Serve HLS playlist for a zone."""

    url = f"{STREAM_URL_PREFIX}/{{zone_id}}/stream.m3u8"
    name = "api:cast_video_to_audio_receivers:playlist"
    requires_auth = False

    async def get(self, request: web.Request, zone_id: str) -> web.Response:
        """Return m3u8 playlist."""
        hass: HomeAssistant = request.app["hass"]
        bridge = _get_bridge_for_zone(hass, zone_id)
        if not bridge:
            return web.Response(status=404, text="Bridge not ready")

        relay = bridge.relays.get(zone_id)
        if not relay or not relay.ffmpeg.is_running:
            return web.Response(status=404, text="No active stream")

        playlist = relay.ffmpeg.playlist_path
        if not playlist.exists():
            return web.Response(status=404, text="Playlist not found")

        body = playlist.read_text(encoding="utf-8")
        return web.Response(
            text=body,
            content_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"},
        )


class StreamSegmentView(HomeAssistantView):
    """Serve HLS segment files."""

    url = f"{STREAM_URL_PREFIX}/{{zone_id}}/{{segment}}"
    name = "api:cast_video_to_audio_receivers:segment"
    requires_auth = False

    async def get(self, request: web.Request, zone_id: str, segment: str) -> web.Response:
        """Return ts segment."""
        if not segment.endswith(".ts"):
            return web.Response(status=404)

        hass: HomeAssistant = request.app["hass"]
        bridge = _get_bridge_for_zone(hass, zone_id)
        if not bridge:
            return web.Response(status=404)

        relay = bridge.relays.get(zone_id)
        if not relay:
            return web.Response(status=404)

        segment_path = relay.ffmpeg.playlist_path.parent / segment
        if not segment_path.exists():
            return web.Response(status=404)

        return web.Response(
            body=segment_path.read_bytes(),
            content_type="video/mp2t",
            headers={"Cache-Control": "no-cache"},
        )


class IpcPlayView(HomeAssistantView):
    """Receive play commands from the cast receiver daemon."""

    url = IPC_PLAY_PATH
    name = "api:cast_video_to_audio_receivers:ipc_play"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Start audio relay for a zone."""
        hass: HomeAssistant = request.app["hass"]
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        zone_id = data.get("zone_id")
        content_id = data.get("content_id") or data.get("url")
        content_type = data.get("content_type")
        custom_data = data.get("custom_data") or {}
        title = data.get("title")

        if not zone_id or not content_id:
            return web.json_response(
                {"ok": False, "error": "zone_id and content_id required"},
                status=400,
            )

        bridge = _get_bridge_for_zone(hass, zone_id)
        if not bridge:
            return web.json_response({"ok": False, "error": "not_ready"}, status=503)

        try:
            await bridge.start_relay(
                zone_id,
                content_id=content_id,
                content_type=content_type,
                custom_data=custom_data,
                title=title,
            )
        except Exception as err:
            _LOGGER.exception("Failed to start relay for zone %s", zone_id)
            return web.json_response({"ok": False, "error": str(err)}, status=500)

        return web.json_response({"ok": True})


class IpcStopView(HomeAssistantView):
    """Receive stop commands from the cast receiver daemon."""

    url = IPC_STOP_PATH
    name = "api:cast_video_to_audio_receivers:ipc_stop"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Stop audio relay."""
        hass: HomeAssistant = request.app["hass"]
        try:
            data = await request.json()
        except Exception:
            data = {}

        zone_id = data.get("zone_id")
        if zone_id:
            bridge = _get_bridge_for_zone(hass, zone_id)
            if bridge:
                await bridge.stop_relay(zone_id)
        else:
            for bridge in hass.data.get(DOMAIN, {}).values():
                if hasattr(bridge, "stop_all"):
                    await bridge.stop_all()

        return web.json_response({"ok": True})


class IpcHealthView(HomeAssistantView):
    """Health check for receiver daemon."""

    url = IPC_HEALTH_PATH
    name = "api:cast_video_to_audio_receivers:ipc_health"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return bridge status."""
        hass: HomeAssistant = request.app["hass"]
        zones: dict = {}
        for bridge in hass.data.get(DOMAIN, {}).values():
            if not hasattr(bridge, "zones"):
                continue
            for zone_id, cfg in bridge.zones.items():
                relay = bridge.relays.get(zone_id)
                if relay:
                    zones[zone_id] = {
                        "friendly_name": cfg["friendly_name"],
                        "target_entity": cfg["target_entity"],
                        "playing": relay.is_playing,
                    }

        if not zones:
            return web.json_response({"ok": False}, status=503)

        return web.json_response({"ok": True, "zones": zones})


def register_views(hass: HomeAssistant) -> None:
    """Register HTTP views."""
    hass.http.register_view(StreamPlaylistView())
    hass.http.register_view(StreamSegmentView())
    hass.http.register_view(IpcPlayView())
    hass.http.register_view(IpcStopView())
    hass.http.register_view(IpcHealthView())
