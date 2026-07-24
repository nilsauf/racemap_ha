"""Exceptions for the RaceMap integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class RaceMapError(HomeAssistantError):
    """Base error for RaceMap."""


class RaceMapAuthError(RaceMapError):
    """Raised when authentication fails (401/403)."""


class RaceMapConnectionError(RaceMapError):
    """Raised on network/timeout/unexpected server errors."""


class RaceMapEventNotFoundError(RaceMapError):
    """Raised when the event id is unknown (404)."""


class RaceMapRateLimitError(RaceMapError):
    """Raised when rate limited (429)."""

    def __init__(self, retry_after: float | None = None) -> None:
        """Store the retry-after hint."""
        super().__init__("RaceMap API rate limit exceeded")
        self.retry_after = retry_after
