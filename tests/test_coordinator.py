"""Tests for the RaceMap coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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


async def test_update_auth_error(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapAuthError("bad")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_update_rate_limit(hass: HomeAssistant, entry: MockConfigEntry) -> None:
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


async def test_logs_only_once_while_unavailable(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repeated connection failures only log the unavailable state once."""
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapConnectionError("down")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)

    with caplog.at_level("WARNING"):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    warnings = [
        record.message
        for record in caplog.records
        if record.levelname == "WARNING"
        and "RaceMap service unavailable" in record.message
    ]
    assert warnings == ["RaceMap service unavailable: down"]


async def test_logs_when_service_recovers(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    current_json: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A success after failure logs one recovery message."""
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = [
        RaceMapConnectionError("down"),
        RaceData.parse(current_json),
    ]
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)

    with caplog.at_level("INFO"):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        data = await coordinator._async_update_data()

    assert data.event.name == current_json["name"]
    infos = [
        record.message
        for record in caplog.records
        if record.levelname == "INFO"
        and record.message == "RaceMap service is available again"
    ]
    assert infos == ["RaceMap service is available again"]
