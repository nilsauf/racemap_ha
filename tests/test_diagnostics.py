"""Tests for RaceMap diagnostics."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.diagnostics import async_get_config_entry_diagnostics
from custom_components.racemap.models import RaceData


async def test_diagnostics_redacts_token(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    """Diagnostics redact credentials and expose coordinator data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "super-secret", CONF_EVENT_ID: "evt123"},
        options={},
        title="Race",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["data"][CONF_TOKEN] != "super-secret"
    assert result["data"]["event"]["name"] == current_json["name"]
    assert len(result["data"]["participants"]) == 3
