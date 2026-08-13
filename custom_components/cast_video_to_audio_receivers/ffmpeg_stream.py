"""FFmpeg audio-only HLS transcoding."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEFAULT_FFMPEG_PATH

_LOGGER = logging.getLogger(__name__)


class FFmpegStream:
    """Manage an FFmpeg subprocess that outputs audio-only HLS."""

    def __init__(
        self,
        hass: HomeAssistant,
        stream_dir: Path,
        ffmpeg_path: str = DEFAULT_FFMPEG_PATH,
        audio_bitrate: str = "128k",
    ) -> None:
        self._hass = hass
        self._stream_dir = stream_dir
        self._ffmpeg_path = ffmpeg_path
        self._audio_bitrate = audio_bitrate
        self._process: asyncio.subprocess.Process | None = None
        self._source_url: str | None = None

    @property
    def is_running(self) -> bool:
        """Return True if ffmpeg is running."""
        return self._process is not None and self._process.returncode is None

    @property
    def playlist_path(self) -> Path:
        """Path to the HLS playlist on disk."""
        return self._stream_dir / "stream.m3u8"

    async def start(self, source_url: str) -> None:
        """Start transcoding source_url to HLS."""
        await self.stop()
        self._source_url = source_url
        self._stream_dir.mkdir(parents=True, exist_ok=True)

        playlist = str(self.playlist_path)
        segment_pattern = str(self._stream_dir / "segment_%03d.ts")

        cmd = [
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            source_url,
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            self._audio_bitrate,
            "-ac",
            "2",
            "-f",
            "hls",
            "-hls_time",
            "2",
            "-hls_list_size",
            "6",
            "-hls_flags",
            "delete_segments+append_list",
            "-hls_segment_filename",
            segment_pattern,
            playlist,
        ]

        ffmpeg = shutil.which(self._ffmpeg_path) or self._ffmpeg_path
        cmd[0] = ffmpeg

        _LOGGER.debug("Starting ffmpeg: %s", " ".join(cmd))
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait briefly for playlist file
        for _ in range(50):
            if self.playlist_path.exists():
                return
            if self._process.returncode is not None:
                stderr = await self._process.stderr.read() if self._process.stderr else b""
                raise RuntimeError(
                    f"FFmpeg exited early ({self._process.returncode}): "
                    f"{stderr.decode(errors='replace')}"
                )
            await asyncio.sleep(0.2)

        raise TimeoutError("FFmpeg did not create HLS playlist in time")

    async def stop(self) -> None:
        """Stop ffmpeg and clean temp files."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

        self._process = None
        self._source_url = None

        if self._stream_dir.exists():
            for path in self._stream_dir.glob("*"):
                try:
                    path.unlink()
                except OSError:
                    pass

    async def read_stderr(self) -> str:
        """Read stderr if process failed."""
        if not self._process or not self._process.stderr:
            return ""
        data = await self._process.stderr.read()
        return data.decode(errors="replace")
