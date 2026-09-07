"""Config flow for Sony BDP-CE.

Two steps: enter the host (and optionally MAC, for Wake-on-LAN), then enter
the PIN the player displays. The PIN shows as on-screen text over HDMI (at
least on the UBP-X700 — it has no front-panel display), so a display fed
from the player needs to be on during this step. See docs/PROTOCOL.md.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResult

from .client import SonyBdpClient
from .const import (
    CONF_CLIENT_ID,
    CONF_MAC,
    CONF_NICKNAME,
    CONF_PIN,
    DEFAULT_CLIENT_ID,
    DEFAULT_NICKNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_MAC): str,
        vol.Optional(CONF_NICKNAME, default=DEFAULT_NICKNAME): str,
    }
)

STEP_PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


class SonyBdpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sony BDP-CE."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._mac: str | None = None
        self._nickname: str = DEFAULT_NICKNAME
        self._client_id: str = DEFAULT_CLIENT_ID

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._mac = user_input.get(CONF_MAC)
            self._nickname = user_input.get(CONF_NICKNAME, DEFAULT_NICKNAME)

            await self.async_set_unique_id(self._mac or self._host)
            self._abort_if_unique_id_configured()

            client = SonyBdpClient(
                host=self._host, client_id=self._client_id, nickname=self._nickname
            )
            try:
                pin_needed = await self.hass.async_add_executor_job(
                    client.begin_pairing
                )
            except requests.exceptions.RequestException:
                errors["base"] = "cannot_connect"
            else:
                if pin_needed:
                    return await self.async_step_pin()
                errors["base"] = "unexpected_response"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            client = SonyBdpClient(
                host=self._host, client_id=self._client_id, nickname=self._nickname
            )
            pin = user_input[CONF_PIN]
            try:
                success = await self.hass.async_add_executor_job(
                    client.complete_pairing, pin
                )
            except requests.exceptions.RequestException:
                errors["base"] = "cannot_connect"
            else:
                if success:
                    return self.async_create_entry(
                        title=self._nickname,
                        data={
                            CONF_HOST: self._host,
                            CONF_MAC: self._mac,
                            CONF_NICKNAME: self._nickname,
                            CONF_CLIENT_ID: self._client_id,
                            CONF_PIN: pin,
                        },
                    )
                errors["base"] = "invalid_pin"

        return self.async_show_form(
            step_id="pin", data_schema=STEP_PIN_SCHEMA, errors=errors
        )
