"""Tests for dynamic participant device registration and removal."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


async def test_cleanup_removes_only_the_stale_entry_device(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Remove this entry's stale device but keep another entry's same-ID device.

    Devices belong to a single config entry, so two entries tracking the same
    participant each own a device with the same identifier.
    """
    participant_0 = current_json["starters"][0]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: []},
        title="Race",
    )
    entry.add_to_hass(hass)
    data = RaceData.parse(current_json)

    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123-second",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_0]},
        title="Race",
    )
    second_entry.add_to_hass(hass)
    participant_identifier = (DOMAIN, f"evt123_{participant_0}")
    stale_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={participant_identifier},
        name="Participant",
    )
    other_device = registry.async_get_or_create(
        config_entry_id=second_entry.entry_id,
        identifiers={participant_identifier},
        name="Participant",
    )
    assert stale_device.id != other_device.id, "devices must be per config entry"

    entry.runtime_data.async_set_updated_data(data)
    await hass.async_block_till_done()

    assert registry.async_get(stale_device.id) is None, "stale device still exists"
    assert (
        registry.async_get_device_by_identifier(participant_identifier, entry.entry_id)
        is None
    ), "stale device is still registered for the entry"
    kept = registry.async_get_device_by_identifier(
        participant_identifier, second_entry.entry_id
    )
    assert kept is not None, "other entry's participant device is missing"
    assert kept.id == other_device.id
    assert kept.config_entry_id == second_entry.entry_id


async def test_cleanup_removes_roster_departures_only_for_current_event(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Remove a departed participant device while keeping unrelated devices."""
    participant_id = current_json["starters"][0]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_id]},
        title="Race",
    )
    entry.add_to_hass(hass)
    data = RaceData.parse(current_json)

    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    foreign_device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "another_event_participant")},
        name="Foreign device",
    )
    stale_data = deepcopy(current_json)
    stale_data["starters"] = [
        participant
        for participant in stale_data["starters"]
        if participant["id"] != participant_id
    ]

    event_identifier = (DOMAIN, entry.entry_id)
    participant_identifier = (DOMAIN, f"evt123_{participant_id}")
    dev_event = registry.async_get_device_by_identifier(
        event_identifier, entry.entry_id
    )
    dev_participant = registry.async_get_device_by_identifier(
        participant_identifier, entry.entry_id
    )

    assert dev_event is not None, "dev_event is None"
    assert dev_participant is not None, "dev_participant is None"
    assert dev_participant.via_device_id == dev_event.id, (
        "participant device is not linked to the event device"
    )

    entry.runtime_data.async_set_updated_data(RaceData.parse(stale_data))
    await hass.async_block_till_done()

    assert registry.async_get(dev_participant.id) is None, (
        "stale participant device still exists"
    )
    assert (
        registry.async_get_device_by_identifier(participant_identifier, entry.entry_id)
        is None
    ), "stale participant device is still registered for the entry"
    assert registry.async_get(dev_event.id) is not None, "event device is missing"
    assert registry.async_get(foreign_device.id) is not None, (
        "foreign device is missing"
    )
