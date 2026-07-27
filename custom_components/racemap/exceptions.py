"""Exceptions for the RaceMap integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


class RaceMapError(HomeAssistantError):
    """Base error for RaceMap.

    Subclasses set a stable ``translation_key`` that maps to the RaceMap
    ``strings.json`` ``exceptions`` section, localized via the RaceMap
    translation domain (``DOMAIN``).
    """

    _translation_key: str | None = None

    def __init__(self, *args: object) -> None:
        """Initialize with the RaceMap translation domain and key."""
        super().__init__(
            *args,
            translation_domain=DOMAIN,
            translation_key=self._translation_key,
        )


class RaceMapAuthError(RaceMapError):
    """Raised when authentication fails (401/403)."""

    _translation_key = "invalid_auth"


class RaceMapConnectionError(RaceMapError):
    """Raised on network/timeout/unexpected server errors."""

    _translation_key = "cannot_connect"


class RaceMapEventNotFoundError(RaceMapError):
    """Raised when the event id is unknown (404)."""

    _translation_key = "event_not_found"


class RaceMapRateLimitError(RaceMapError):
    """Raised when rate limited (429)."""

    _translation_key = "rate_limited"

    def __init__(self, retry_after: float | None = None) -> None:
        """Store the retry-after hint."""
        super().__init__()
        self.retry_after = retry_after
