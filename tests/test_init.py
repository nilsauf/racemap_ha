"""Tests for RaceMap setup/unload."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.exceptions import RaceMapConnectionError
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={},
        unique_id="evt123",
        title="Race",
    )


async def test_setup_and_unload(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        side_effect=RaceMapConnectionError("down"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
