"""Tests for RaceMap sensors."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
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
    """Set up an entry with coordinator data and the real sensor platform."""
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.racemap.RaceMapApiClient.async_get_current",
            return_value=data,
        ),
        patch("custom_components.racemap.PLATFORMS", [Platform.SENSOR]),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_event_sensors_created(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """Create event sensors from coordinator data."""
    await _setup(hass, entry, RaceData.parse(current_json))

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_participant_count"
    )

    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "3"


async def test_participant_speed_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """Create the selected participant's speed sensor."""
    await _setup(hass, entry, RaceData.parse(current_json))
    participant_id = current_json["starters"][0]["id"]

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"evt123_{participant_id}_speed"
    )

    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == current_json["starters"][0]["current"]["speed"]


async def test_diagnostic_sensor_absent_when_no_device(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Do not create device diagnostic sensors without a tracker device."""
    participant = next(
        starter for starter in current_json["starters"] if starter.get("device") is None
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant["id"]]},
        title="Race",
    )

    await _setup(hass, entry, RaceData.parse(current_json))

    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"evt123_{participant['id']}_battery"
    )

    assert entity_id is None
