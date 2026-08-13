"""SVT Play stream URL resolver."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from ..const import SVT_FORMATS

_LOGGER = logging.getLogger(__name__)

SVT_CHANNEL_API = "https://api.svt.se/videoplayer-api/video/ch-{channel}"
SVT_VIDEO_API = "https://api.svt.se/video/{video_id}"


async def resolve_channel_url(
    session: aiohttp.ClientSession, channel: str, formats: list[str] | None = None
) -> str:
    """Resolve a live channel name to a stream URL."""
    url = SVT_CHANNEL_API.format(channel=channel.lower())
    return await _resolve_from_api(session, url, formats or SVT_FORMATS)


async def resolve_video_url(
    session: aiohttp.ClientSession, video_id: str, formats: list[str] | None = None
) -> str:
    """Resolve a SVT video id to a stream URL."""
    url = SVT_VIDEO_API.format(video_id=video_id)
    return await _resolve_from_api(session, url, formats or SVT_FORMATS)


async def _resolve_from_api(
    session: aiohttp.ClientSession, api_url: str, formats: list[str]
) -> str:
    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        resp.raise_for_status()
        data: dict[str, Any] = await resp.json()

    if error := data.get("error"):
        raise ValueError(f"SVT API error: {error}")

    references = data.get("videoReferences", [])
    for fmt in formats:
        for ref in references:
            if ref.get("format") == fmt and ref.get("url"):
                return ref["url"]

    raise ValueError(f"No supported stream format found for {api_url}")


def extract_playable_url(content_id: str, content_type: str | None = None) -> str | None:
    """Return a direct URL if content_id is already playable."""
    if not content_id:
        return None
    if content_id.startswith(("http://", "https://")):
        return content_id
    return None


async def resolve_content(
    session: aiohttp.ClientSession,
    content_id: str,
    content_type: str | None = None,
    custom_data: dict[str, Any] | None = None,
) -> str:
    """Best-effort resolve cast media to a stream URL."""
    direct = extract_playable_url(content_id, content_type)
    if direct:
        return direct

    custom_data = custom_data or {}
    if channel := custom_data.get("channel"):
        return await resolve_channel_url(session, str(channel))

    if video_id := custom_data.get("videoId") or custom_data.get("video_id"):
        return await resolve_video_url(session, str(video_id))

    # SVT sometimes sends slug-like content ids for channels
    known_channels = {"svt1", "svt2", "svt24", "barnkanalen", "kunskapskanalen"}
    lowered = content_id.lower().strip()
    if lowered in known_channels:
        return await resolve_channel_url(session, lowered)

    raise ValueError(f"Could not resolve stream URL from content_id={content_id!r}")
