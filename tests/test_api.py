"""Tests for the RaceMap API client."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from custom_components.racemap.api import RaceMapApiClient
from custom_components.racemap.const import DOMAIN
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)

EVENT_ID = "evt123"


@pytest.mark.parametrize(
    ("exc", "translation_key"),
    [
        (RaceMapAuthError(), "invalid_auth"),
        (RaceMapConnectionError(), "cannot_connect"),
        (RaceMapEventNotFoundError(), "event_not_found"),
        (RaceMapRateLimitError(), "rate_limited"),
    ],
)
def test_exceptions_carry_translation_metadata(
    exc: RaceMapError, translation_key: str
) -> None:
    """Each RaceMap exception localizes via the RaceMap translation domain."""
    assert exc.translation_domain == DOMAIN
    assert exc.translation_key == translation_key


def test_rate_limit_exception_keeps_retry_after() -> None:
    """The rate-limit exception retains its retry_after hint."""
    exc = RaceMapRateLimitError(retry_after=12.5)
    assert exc.retry_after == 12.5
    assert exc.translation_domain == DOMAIN
    assert exc.translation_key == "rate_limited"


URL = f"https://racemap.com/api/data/v1/{EVENT_ID}/current"


class RequestContext:
    """Response context that also supports the previous awaitable request path."""

    def __init__(self, response: MagicMock) -> None:
        """Store the response and track context-manager cleanup."""
        self.response = response
        self.exited = False

    def __await__(self) -> Any:
        """Return the response for the pre-context-manager implementation."""

        async def get_response() -> MagicMock:
            return self.response

        return get_response().__await__()

    async def __aenter__(self) -> MagicMock:
        """Enter the response context."""
        return self.response

    async def __aexit__(self, *args: object) -> None:
        """Record response context cleanup."""
        self.exited = True


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


@pytest.mark.parametrize(
    "retry_after", ["later", "Wed, 21 Oct 2015 07:28:00 GMT", "-1", "nan", "inf"]
)
async def test_get_current_rate_limited_with_nondelta_retry_after(
    retry_after: str,
) -> None:
    """Raise the integration error and close the response for every 429 hint."""
    response = MagicMock(status=429, headers={"Retry-After": retry_after})
    request = RequestContext(response)
    session = MagicMock()
    session.get.return_value = request
    api_client = RaceMapApiClient(session, "secret-token", EVENT_ID)

    with pytest.raises(RaceMapRateLimitError) as err:
        await api_client.async_get_current()

    assert err.value.retry_after is None
    assert request.exited


async def test_get_current_non_mapping_json_raises_connection_error() -> None:
    """Wrap a valid JSON response with an unexpected top-level shape."""
    response = MagicMock(status=200, headers={})
    response.json = AsyncMock(return_value=[])
    request = RequestContext(response)
    session = MagicMock()
    session.get.return_value = request
    api_client = RaceMapApiClient(session, "secret-token", EVENT_ID)

    with pytest.raises(RaceMapConnectionError):
        await api_client.async_get_current()


async def test_get_current_malformed_json_raises_connection_error() -> None:
    """Wrap malformed JSON payload errors in an integration exception."""
    response = MagicMock(status=200, headers={})
    response.json = AsyncMock(
        side_effect=json.JSONDecodeError("Expecting value", "", 0)
    )
    request = RequestContext(response)
    session = MagicMock()
    session.get.return_value = request
    api_client = RaceMapApiClient(session, "secret-token", EVENT_ID)

    with pytest.raises(RaceMapConnectionError):
        await api_client.async_get_current()


async def test_get_current_json_client_error_raises_connection_error() -> None:
    """Wrap aiohttp payload-read errors in an integration exception."""
    response = MagicMock(status=200, headers={})
    response.json = AsyncMock(side_effect=aiohttp.ClientError("read failed"))
    request = RequestContext(response)
    session = MagicMock()
    session.get.return_value = request
    api_client = RaceMapApiClient(session, "secret-token", EVENT_ID)

    with pytest.raises(RaceMapConnectionError):
        await api_client.async_get_current()


async def test_get_current_network_error(client: RaceMapApiClient) -> None:
    with aioresponses() as m:
        m.get(URL, exception=TimeoutError())
        with pytest.raises(RaceMapConnectionError):
            await client.async_get_current()
