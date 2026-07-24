"""Tests for the RaceMap coordinator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.coordinator import RaceMapDataUpdateCoordinator
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapRateLimitError,
)
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={},
        unique_id="evt123",
    )


async def test_update_success(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.return_value = RaceData.parse(current_json)
    entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data.event.name == current_json["name"]


async def test_update_auth_error(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapAuthError("bad")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_update_rate_limit(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapRateLimitError(30.0)
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()
    assert err.value.__cause__.translation_key == "rate_limited"
    assert getattr(err.value, "retry_after", None) == 30.0


async def test_update_connection_error(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapConnectionError("down")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
