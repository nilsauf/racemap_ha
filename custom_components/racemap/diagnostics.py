"""Diagnostics support for RaceMap."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import RaceMapConfigEntry

TO_REDACT = {CONF_TOKEN, "Authorization"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RaceMapConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "data": {
            "event": asdict(data.event),
            "participants": [asdict(participant) for participant in data.participants],
        },
    }
