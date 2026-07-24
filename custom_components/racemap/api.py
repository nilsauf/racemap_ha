"""RaceMap API client."""

from __future__ import annotations

import asyncio
import time

import aiohttp

from .const import BASE_URL, LOGGER, REQUEST_TIMEOUT
from .exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)
from .models import RaceData


class RaceMapApiClient:
    """Client for the RaceMap live data API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        event_id: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._token = token
        self._event_id = event_id

    @property
    def _url(self) -> str:
        """Return the /current endpoint URL."""
        return f"{BASE_URL}/api/data/v1/{self._event_id}/current"

    async def async_get_current(self) -> RaceData:
        """Fetch and parse the current race data."""
        headers = {"Authorization": f"Bearer {self._token}"}
        started = time.monotonic()
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(self._url, headers=headers)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RaceMapConnectionError(
                f"Error connecting to RaceMap: {err}"
            ) from err

        LOGGER.debug(
            "RaceMap GET /current event=%s status=%s duration=%.3fs",
            self._event_id,
            response.status,
            time.monotonic() - started,
        )

        if response.status in (401, 403):
            raise RaceMapAuthError("Invalid RaceMap API token")
        if response.status == 404:
            raise RaceMapEventNotFoundError(
                f"RaceMap event {self._event_id} not found"
            )
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RaceMapRateLimitError(
                float(retry_after) if retry_after else None
            )
        if response.status >= 400:
            raise RaceMapConnectionError(
                f"Unexpected RaceMap status {response.status}"
            )

        payload = await response.json()
        data = RaceData.parse(payload)
        LOGGER.debug("RaceMap parsed %d participants", len(data.participants))
        return data
