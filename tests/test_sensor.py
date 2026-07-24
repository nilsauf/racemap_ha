"""Tests for RaceMap sensors."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData
from custom_components.racemap.sensor import PARTICIPANT_SENSORS

# Extrapolated sensor key -> (base key, device_class, state_class, unit)
EXTRAPOLATED_METADATA = {
    "from_start_ex": (
        "from_start",
        SensorDeviceClass.DISTANCE,
        SensorStateClass.TOTAL,
        UnitOfLength.METERS,
    ),
    "to_finish_ex": (
        "to_finish",
        SensorDeviceClass.DISTANCE,
        SensorStateClass.MEASUREMENT,
        UnitOfLength.METERS,
    ),
    "gap_distance_ex": (
        "gap_distance",
        SensorDeviceClass.DISTANCE,
        SensorStateClass.MEASUREMENT,
        UnitOfLength.METERS,
    ),
    "gap_ex": (
        "gap",
        SensorDeviceClass.DURATION,
        SensorStateClass.MEASUREMENT,
        UnitOfTime.SECONDS,
    ),
    "gap_chase_ex": (
        "gap_chase",
        SensorDeviceClass.DURATION,
        SensorStateClass.MEASUREMENT,
        UnitOfTime.SECONDS,
    ),
    "gap_average_ex": (
        "gap_average",
        SensorDeviceClass.DURATION,
        SensorStateClass.MEASUREMENT,
        UnitOfTime.SECONDS,
    ),
}


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


def test_extrapolated_sensor_inventory() -> None:
    """The six extrapolated descriptions exist with mirrored base metadata."""
    by_key = {desc.key: desc for desc in PARTICIPANT_SENSORS}

    for ex_key, (base_key, device_class, state_class, unit) in (
        EXTRAPOLATED_METADATA.items()
    ):
        assert ex_key in by_key, f"missing extrapolated sensor {ex_key}"
        assert base_key in by_key, f"missing base sensor {base_key}"

        ex = by_key[ex_key]
        base = by_key[base_key]

        # Disabled by default.
        assert ex.entity_registry_enabled_default is False, ex_key

        # Metadata mirrors the base field.
        assert ex.device_class == device_class, ex_key
        assert ex.state_class == state_class, ex_key
        assert ex.native_unit_of_measurement == unit, ex_key

        # And matches the actual base description too.
        assert ex.device_class == base.device_class, ex_key
        assert ex.state_class == base.state_class, ex_key
        assert (
            ex.native_unit_of_measurement == base.native_unit_of_measurement
        ), ex_key

        # Translation key mirrors its own key.
        assert ex.translation_key == ex_key, ex_key


def test_extrapolated_sensor_value_fn_reads_current_attribute(
    current_json: dict[str, Any],
) -> None:
    """Each extrapolated value_fn reads the matching ParticipantCurrent field."""
    by_key = {desc.key: desc for desc in PARTICIPANT_SENSORS}
    data = RaceData.parse(current_json)
    participant = data.participants[0]

    for ex_key in EXTRAPOLATED_METADATA:
        desc = by_key[ex_key]
        expected = getattr(participant.current, ex_key)
        assert desc.value_fn(participant) == expected, ex_key
