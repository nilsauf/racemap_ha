"""Constants for the RaceMap integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "racemap"
LOGGER: Final = logging.getLogger(__package__)

BASE_URL: Final = "https://racemap.com"
REQUEST_TIMEOUT: Final = 10

# HTTP status codes handled by the API client.
HTTP_UNAUTHORIZED: Final = 401
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_TOO_MANY_REQUESTS: Final = 429
HTTP_BAD_REQUEST: Final = 400

CONF_TOKEN: Final = "token"  # noqa: S105 - config key name, not a secret value
CONF_EVENT_ID: Final = "event_id"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_PARTICIPANTS: Final = "participants"

DEFAULT_UPDATE_INTERVAL: Final = 30
MIN_UPDATE_INTERVAL: Final = 5

ATTRIBUTION: Final = "Data provided by RaceMap"
MANUFACTURER: Final = "RaceMap"
