"""Tests for the RaceMap API client."""

from __future__ import annotations

from typing import Any

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from custom_components.racemap.api import RaceMapApiClient
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)

EVENT_ID = "evt123"
URL = f"https://racemap.com/api/data/v1/{EVENT_ID}/current"


@pytest.fixture
async def client() -> RaceMapApiClient:
    async with ClientSession() as session:
        yield RaceMapApiClient(session, "secret-token", EVENT_ID)


async def test_get_current_success(
    client: RaceMapApiClient, current_json: dict[str, Any]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=200, payload=current_json)
        data = await client.async_get_current()
    assert data.event.name == current_json["name"]
    assert len(data.participants) == 3


async def test_get_current_sends_bearer_token(
    client: RaceMapApiClient, current_json: dict[str, Any]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=200, payload=current_json)
        await client.async_get_current()
        request = next(iter(m.requests.values()))[0]
    assert request.kwargs["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, RaceMapAuthError),
        (403, RaceMapAuthError),
        (404, RaceMapEventNotFoundError),
        (500, RaceMapConnectionError),
        (502, RaceMapConnectionError),
    ],
)
async def test_get_current_status_errors(
    client: RaceMapApiClient, status: int, expected: type[Exception]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=status)
        with pytest.raises(expected):
            await client.async_get_current()


async def test_get_current_rate_limited(client: RaceMapApiClient) -> None:
    with aioresponses() as m:
        m.get(URL, status=429, headers={"Retry-After": "42"})
        with pytest.raises(RaceMapRateLimitError) as err:
            await client.async_get_current()
    assert err.value.retry_after == 42.0


async def test_get_current_network_error(client: RaceMapApiClient) -> None:
    with aioresponses() as m:
        m.get(URL, exception=TimeoutError())
        with pytest.raises(RaceMapConnectionError):
            await client.async_get_current()
