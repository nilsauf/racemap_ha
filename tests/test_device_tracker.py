"""Tests for the RaceMap device tracker."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry(current_json: dict[str, Any]) -> MockConfigEntry:
    """Return an entry selecting the first participant."""
    participant_id = current_json["starters"][0]["id"]
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_id]},
        title="Race",
    )


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, data: RaceData
) -> None:
    """Set up an entry with supplied coordinator data."""
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_tracker_reports_coordinates(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """Expose a selected participant's current GPS coordinates."""
    await _setup(hass, entry, RaceData.parse(current_json))
    participant_id = current_json["starters"][0]["id"]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{participant_id}_tracker"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    current = current_json["starters"][0]["current"]
    assert state.attributes["latitude"] == current["lat"]
    assert state.attributes["longitude"] == current["lng"]


async def test_tracker_unavailable_without_location(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Mark the tracker unavailable when current location is absent."""
    payload = copy.deepcopy(current_json)
    payload["starters"][0]["current"] = None
    participant_id = payload["starters"][0]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_id]},
        title="Race",
    )
    await _setup(hass, entry, RaceData.parse(payload))
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{participant_id}_tracker"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unavailable"
