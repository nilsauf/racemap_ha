"""Tests for dynamic participant device registration and removal."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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


async def test_deselecting_participant_removes_only_its_device(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Remove deselected participant devices but keep event and foreign devices."""
    participant_0 = current_json["starters"][0]["id"]
    participant_1 = current_json["starters"][1]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [participant_0, participant_1]},
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

    dev_event = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    dev_p1 = registry.async_get_device(identifiers={(DOMAIN, f"evt123_{participant_1}")})

    assert dev_event is not None, "dev_event is None"
    assert dev_p1 is not None, "dev_p1 is None"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 60,
            CONF_PARTICIPANTS: [participant_0],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert registry.async_get_device({(DOMAIN, f"evt123_{participant_0}")}) is not None, "participant_0 is missing"
    assert registry.async_get_device({(DOMAIN, f"evt123_{participant_1}")}) is None, "participant_1 is NOT missing"
    assert registry.async_get_device({(DOMAIN, entry.entry_id)}) is not None, "event device is missing"
    assert registry.async_get_device(foreign_device.identifiers) is not None, "foreign device is missing"
