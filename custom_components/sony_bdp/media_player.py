"""Media player entity for a Sony BDP-CE Blu-ray player."""

from __future__ import annotations

import logging

import requests
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import PairingRequired, TransportState
from .const import CONF_NICKNAME, DOMAIN
from .coordinator import SonyBdpCoordinator

_LOGGER = logging.getLogger(__name__)

_STATE_MAP = {
    TransportState.PLAYING: MediaPlayerState.PLAYING,
    TransportState.PAUSED: MediaPlayerState.PAUSED,
    TransportState.STOPPED: MediaPlayerState.IDLE,
    TransportState.NO_MEDIA: MediaPlayerState.IDLE,
    TransportState.TRANSITIONING: MediaPlayerState.IDLE,
    TransportState.UNKNOWN: MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SonyBdpCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SonyBdpMediaPlayer(coordinator, entry)])


class SonyBdpMediaPlayer(CoordinatorEntity[SonyBdpCoordinator], MediaPlayerEntity):
    """Represents the player's playback and power state."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: SonyBdpCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=entry.data.get(CONF_NICKNAME, "Sony BDP-CE"),
            manufacturer="Sony",
            model="BDP-CE",
        )

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.TURN_OFF
        )
        if self.coordinator.client.mac:
            features |= MediaPlayerEntityFeature.TURN_ON
        return features

    @property
    def state(self) -> MediaPlayerState:
        data = self.coordinator.data
        if data is None or not data.reachable:
            return MediaPlayerState.OFF
        return _STATE_MAP.get(data.transport_state, MediaPlayerState.IDLE)

    async def _async_send(self, name: str, action) -> None:
        try:
            await self.hass.async_add_executor_job(action)
        except PairingRequired:
            _LOGGER.warning(
                "%s: not paired yet, can't send %s — reconfigure the integration",
                self.entity_id,
                name,
            )
        except requests.exceptions.RequestException as err:
            _LOGGER.warning("%s: %s command failed: %s", self.entity_id, name, err)
        else:
            await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        await self._async_send("play", self.coordinator.client.play)

    async def async_media_pause(self) -> None:
        await self._async_send("pause", self.coordinator.client.pause)

    async def async_media_stop(self) -> None:
        await self._async_send("stop", self.coordinator.client.stop)

    async def async_turn_off(self) -> None:
        await self._async_send("power", self.coordinator.client.power)

    async def async_turn_on(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.wake_on_lan)
        await self.coordinator.async_request_refresh()
