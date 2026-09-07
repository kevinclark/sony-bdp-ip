"""Polling coordinator for a Sony BDP-CE device."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client import SonyBdpClient, TransportState
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


@dataclass
class SonyBdpData:
    """Latest known state of the player."""

    reachable: bool
    transport_state: TransportState | None


class SonyBdpCoordinator(DataUpdateCoordinator[SonyBdpData]):
    """Polls transport state. Treats connection failure as 'powered off'.

    The player drops off the network entirely in full standby (relying on
    Wake-on-LAN at the Ethernet frame level, no IP stack involved) — see
    docs/PROTOCOL.md. So a connection failure here is the expected, normal
    way we learn the player is off, not an integration error.
    """

    def __init__(self, hass: HomeAssistant, client: SonyBdpClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> SonyBdpData:
        try:
            state = await self.hass.async_add_executor_job(
                self.client.get_transport_state
            )
        except requests.exceptions.RequestException:
            return SonyBdpData(reachable=False, transport_state=None)
        return SonyBdpData(reachable=True, transport_state=state)
