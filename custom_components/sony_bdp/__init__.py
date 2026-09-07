"""The Sony BDP-CE integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .client import SonyBdpClient
from .const import CONF_CLIENT_ID, CONF_MAC, CONF_NICKNAME, CONF_PIN, DOMAIN
from .coordinator import SonyBdpCoordinator

PLATFORMS = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = SonyBdpClient(
        host=entry.data[CONF_HOST],
        client_id=entry.data[CONF_CLIENT_ID],
        nickname=entry.data[CONF_NICKNAME],
        mac=entry.data.get(CONF_MAC),
        pin=entry.data.get(CONF_PIN),
    )
    coordinator = SonyBdpCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
