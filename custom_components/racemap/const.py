"""Constants for the RaceMap integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "racemap"
LOGGER: Final = logging.getLogger(__package__)

BASE_URL: Final = "https://racemap.com"
REQUEST_TIMEOUT: Final = 10

CONF_TOKEN: Final = "token"
CONF_EVENT_ID: Final = "event_id"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_PARTICIPANTS: Final = "participants"

DEFAULT_UPDATE_INTERVAL: Final = 30
MIN_UPDATE_INTERVAL: Final = 5

ATTRIBUTION: Final = "Data provided by RaceMap"
MANUFACTURER: Final = "RaceMap"
