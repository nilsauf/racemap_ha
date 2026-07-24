"""Tests for the RaceMap config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
)
from custom_components.racemap.models import RaceData

USER_INPUT = {CONF_TOKEN: "secret", CONF_EVENT_ID: "evt123"}


def _patch_get_current(current_json: dict[str, Any], **kw: Any):
    return patch(
        "custom_components.racemap.config_flow.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
        **kw,
    )


async def test_user_flow_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == "evt123"


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (RaceMapAuthError("x"), "invalid_auth"),
        (RaceMapEventNotFoundError("x"), "event_not_found"),
        (RaceMapConnectionError("x"), "cannot_connect"),
        (ValueError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, exc: Exception, error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(
        "custom_components.racemap.config_flow.RaceMapApiClient.async_get_current",
        side_effect=exc,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_duplicate(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT).add_to_hass(
        hass
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "newtoken"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "newtoken"


async def test_reconfigure_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "t2", CONF_EVENT_ID: "evt123"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_TOKEN] == "t2"


async def test_options_flow(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="evt123", data=USER_INPUT, options={}
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        participant_id = current_json["starters"][0]["id"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_UPDATE_INTERVAL: 60, CONF_PARTICIPANTS: [participant_id]},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 60
    assert entry.options[CONF_PARTICIPANTS] == [participant_id]


def _participant_option_values(result: dict[str, Any]) -> list[str]:
    """Extract selector option values for the participants field."""
    schema = result["data_schema"].schema
    for key, selector in schema.items():
        if key == CONF_PARTICIPANTS:
            return [
                option["value"]
                for option in selector.config["options"]
            ]
    return []


async def test_options_flow_fallback_to_stored_ids(hass: HomeAssistant) -> None:
    """Stored participant IDs are offered when no coordinator data exists."""
    stored_ids = ["starter-a", "starter-b"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data=USER_INPUT,
        options={CONF_PARTICIPANTS: stored_ids},
    )
    entry.add_to_hass(hass)
    # Do not set up the entry: no runtime_data / coordinator.data available.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert _participant_option_values(result) == stored_ids
