"""Tests for dynamic participant device registration and removal."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


async def test_cleanup_removes_only_the_stale_entry_association(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Keep a participant device associated with another selected entry."""
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
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={participant_identifier},
        name="Participant",
    )
    registry.async_update_device(device.id, add_config_entry_id=second_entry.entry_id)

    entry.runtime_data.async_set_updated_data(data)
    await hass.async_block_till_done()

    device = registry.async_get(device.id)
    assert device is not None, "participant device is missing"
    assert entry.entry_id not in device.config_entries
    assert second_entry.entry_id in device.config_entries


async def test_cleanup_removes_roster_departures_only_for_current_event(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Remove stale participant association while keeping unrelated devices."""
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

    dev_event = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    dev_participant = registry.async_get_device(
        identifiers={(DOMAIN, f"evt123_{participant_id}")}
    )

    assert dev_event is not None, "dev_event is None"
    assert dev_participant is not None, "dev_participant is None"

    entry.runtime_data.async_set_updated_data(RaceData.parse(stale_data))
    await hass.async_block_till_done()

    assert registry.async_get_device(
        identifiers={(DOMAIN, f"evt123_{participant_id}")}
    ) is None, "participant device still has the stale entry association"
    assert registry.async_get_device({(DOMAIN, entry.entry_id)}) is not None, "event device is missing"
    assert registry.async_get_device(foreign_device.identifiers) is not None, "foreign device is missing"
