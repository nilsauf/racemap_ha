"""RaceMap API client."""

from __future__ import annotations

import asyncio
import math
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
                async with self._session.get(self._url, headers=headers) as response:
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
                        try:
                            retry_after_seconds = (
                                float(retry_after) if retry_after else None
                            )
                        except (TypeError, ValueError):
                            retry_after_seconds = None
                        if retry_after_seconds is not None and (
                            not math.isfinite(retry_after_seconds)
                            or retry_after_seconds < 0
                        ):
                            retry_after_seconds = None
                        raise RaceMapRateLimitError(retry_after_seconds)
                    if response.status >= 400:
                        raise RaceMapConnectionError(
                            f"Unexpected RaceMap status {response.status}"
                        )

                    payload = await response.json()
                    if not isinstance(payload, dict):
                        raise ValueError("RaceMap response must be a JSON object")
                    data = RaceData.parse(payload)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RaceMapConnectionError(
                f"Error connecting to RaceMap: {err}"
            ) from err
        except ValueError as err:
            raise RaceMapConnectionError(
                f"Error reading RaceMap response: {err}"
            ) from err
        LOGGER.debug("RaceMap parsed %d participants", len(data.participants))
        return data
