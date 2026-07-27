"""Tests for the RaceMap device tracker."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.device_tracker import SourceType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.device_tracker import RaceMapDeviceTracker
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


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: RaceData) -> None:
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


async def test_tracker_uses_tracker_translation_key(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """The tracker entity registry entry uses translation_key 'tracker'."""
    await _setup(hass, entry, RaceData.parse(current_json))
    participant_id = current_json["starters"][0]["id"]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{participant_id}_tracker"
    )
    assert entity_id is not None
    registry_entry = registry.async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.translation_key == "tracker"


async def test_tracker_reports_gps_source_type(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """The tracker advertises a GPS source type."""
    await _setup(hass, entry, RaceData.parse(current_json))
    participant_id = current_json["starters"][0]["id"]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{participant_id}_tracker"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["source_type"] == SourceType.GPS


def _make_tracker(
    current_json: dict[str, Any],
    participant_id: str,
) -> RaceMapDeviceTracker:
    """Build a tracker backed by a stub coordinator, bypassing HA setup."""
    data = RaceData.parse(current_json)
    coordinator = MagicMock()
    coordinator.data = data
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_id]},
        title="Race",
    )
    return RaceMapDeviceTracker(coordinator, entry, participant_id)


def test_latitude_longitude_none_when_participant_gone(
    current_json: dict[str, Any],
) -> None:
    """Coordinates and availability fall back to None when data is gone."""
    participant_id = current_json["starters"][0]["id"]
    tracker = _make_tracker(current_json, participant_id)

    # Drop the participant from the latest coordinator data.
    tracker.coordinator.data = RaceData.parse({"starters": []})

    assert tracker._participant is None
    assert tracker.latitude is None
    assert tracker.longitude is None
    assert tracker.available is False


def test_latitude_longitude_none_when_current_missing(
    current_json: dict[str, Any],
) -> None:
    """Coordinates return None when a participant has no current location."""
    # starter-c has current == null in the fixture.
    payload = copy.deepcopy(current_json)
    participant_id = "starter-a"
    payload["starters"][0]["current"] = None
    tracker = _make_tracker(payload, participant_id)

    assert tracker._participant is not None
    assert tracker._participant.current is None
    assert tracker.latitude is None
    assert tracker.longitude is None


async def test_tracker_skips_already_known_participant(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    """Re-running the listener does not re-add an already-known tracker."""
    await _setup(hass, entry, RaceData.parse(current_json))
    participant_id = current_json["starters"][0]["id"]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{participant_id}_tracker"
    )
    assert entity_id is not None

    coordinator = entry.runtime_data
    before = len(hass.states.async_entity_ids("device_tracker"))
    # Push the same data again; the listener must hit the "already known"
    # branch and add no new entities.
    coordinator.async_set_updated_data(RaceData.parse(current_json))
    await hass.async_block_till_done()
    after = len(hass.states.async_entity_ids("device_tracker"))
    assert after == before
