"""DataUpdateCoordinator for RaceMap."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .exceptions import (
    RaceMapAuthError,
    RaceMapError,
    RaceMapRateLimitError,
)
from .models import RaceData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import RaceMapApiClient

type RaceMapConfigEntry = ConfigEntry[RaceMapDataUpdateCoordinator]


class RaceMapDataUpdateCoordinator(DataUpdateCoordinator[RaceData]):
    """Coordinate a single /current poll for all entities."""

    config_entry: RaceMapConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RaceMapConfigEntry,
        client: RaceMapApiClient,
    ) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )
        self.client = client
        self._service_available: bool | None = None

    def _mark_service_available(self) -> None:
        """Log once when the service recovers."""
        if self._service_available is False:
            LOGGER.info("RaceMap service is available again")
        self._service_available = True

    def _mark_service_unavailable(self, message: str, *args: object) -> None:
        """Log once when the service becomes unavailable."""
        if self._service_available is not False:
            LOGGER.warning(message, *args)
        self._service_available = False

    async def _async_update_data(self) -> RaceData:
        """Fetch data from the RaceMap API."""
        try:
            data = await self.client.async_get_current()
        except RaceMapAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except RaceMapRateLimitError as err:
            self._mark_service_unavailable(
                "RaceMap API rate limit exceeded; retrying later"
            )
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except RaceMapError as err:
            self._mark_service_unavailable("RaceMap service unavailable: %s", err)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        self._mark_service_available()
        return data
