"""The RaceMap integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RaceMapApiClient
from .const import CONF_EVENT_ID, CONF_TOKEN
from .coordinator import RaceMapDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import RaceMapConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


async def async_setup_entry(hass: HomeAssistant, entry: RaceMapConfigEntry) -> bool:
    """Set up RaceMap from a config entry."""
    session = async_get_clientsession(hass)
    client = RaceMapApiClient(
        session, entry.data[CONF_TOKEN], entry.data[CONF_EVENT_ID]
    )
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RaceMapConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
