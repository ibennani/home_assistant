"""Config flow for Cast video to audio receivers."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    CONF_CERT_MANIFEST,
    CONF_ENABLE_MONITOR,
    CONF_FRIENDLY_NAME,
    CONF_MONITOR_VIDEO_ENTITY,
    CONF_TARGET_ENTITY,
    CONF_ZONE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or str(uuid.uuid4())[:8]


class CastVideoAudioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Add first or additional zone."""
        errors: dict[str, str] = {}

        if user_input is not None:
            friendly_name = user_input[CONF_FRIENDLY_NAME].strip()
            zone_id = _slugify(friendly_name)
            cert_path = user_input.get(CONF_CERT_MANIFEST, "").strip()

            if not user_input.get(CONF_TARGET_ENTITY):
                errors["base"] = "invalid_target"
            elif cert_path and not Path(cert_path).exists():
                errors["base"] = "cert_missing"
            else:
                entry = await self.async_set_unique_id(zone_id)
                if entry:
                    return self.async_abort(reason="already_configured")

                zone = {
                    CONF_ZONE_ID: zone_id,
                    CONF_FRIENDLY_NAME: friendly_name,
                    CONF_TARGET_ENTITY: user_input[CONF_TARGET_ENTITY],
                    CONF_CERT_MANIFEST: cert_path,
                    CONF_ENABLE_MONITOR: user_input.get(CONF_ENABLE_MONITOR, False),
                    CONF_MONITOR_VIDEO_ENTITY: user_input.get(CONF_MONITOR_VIDEO_ENTITY),
                }

                return self.async_create_entry(
                    title=friendly_name,
                    data={"zones": {zone_id: zone}},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_FRIENDLY_NAME): str,
                vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(CONF_CERT_MANIFEST, default=""): str,
                vol.Optional(CONF_ENABLE_MONITOR, default=False): bool,
                vol.Optional(CONF_MONITOR_VIDEO_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow."""
        return CastVideoAudioOptionsFlow(config_entry)


class CastVideoAudioOptionsFlow(config_entries.OptionsFlow):
    """Options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Edit ffmpeg options."""
        from .const import CONF_AUDIO_BITRATE, CONF_FFMPEG_PATH, DEFAULT_AUDIO_BITRATE, DEFAULT_FFMPEG_PATH

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FFMPEG_PATH,
                    default=self.config_entry.options.get(CONF_FFMPEG_PATH, DEFAULT_FFMPEG_PATH),
                ): str,
                vol.Optional(
                    CONF_AUDIO_BITRATE,
                    default=self.config_entry.options.get(CONF_AUDIO_BITRATE, DEFAULT_AUDIO_BITRATE),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
