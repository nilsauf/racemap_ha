"""Typed data models for the RaceMap integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from homeassistant.util import dt as dt_util

from .const import LOGGER


def _f(value: Any) -> float | None:
    """Coerce to float or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    """Parse an ISO timestamp to an aware datetime or None."""
    if not value:
        return None
    return dt_util.parse_datetime(str(value))


@dataclass(frozen=True, slots=True)
class ParticipantCurrent:
    """Live location/timing data for a participant."""

    time: datetime | None
    lat: float | None
    lng: float | None
    elv: float | None
    speed: float | None
    distance_to_shadow_track: float | None
    speed_st: float | None
    elv_st: float | None
    from_start: float | None
    to_finish: float | None
    eta: float | None
    gap: float | None
    gap_chase: float | None
    gap_average: float | None
    gap_distance: float | None
    from_start_ex: float | None
    to_finish_ex: float | None
    gap_ex: float | None
    gap_chase_ex: float | None
    gap_average_ex: float | None
    gap_distance_ex: float | None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Self:
        """Parse the current object."""
        return cls(
            time=_dt(raw.get("time")),
            lat=_f(raw.get("lat")),
            lng=_f(raw.get("lng")),
            elv=_f(raw.get("elv")),
            speed=_f(raw.get("speed")),
            distance_to_shadow_track=_f(raw.get("distanceToShadowTrack")),
            speed_st=_f(raw.get("speedSt")),
            elv_st=_f(raw.get("elvSt")),
            from_start=_f(raw.get("fromStart")),
            to_finish=_f(raw.get("toFinish")),
            eta=_f(raw.get("eta")),
            gap=_f(raw.get("gap")),
            gap_chase=_f(raw.get("gapChase")),
            gap_average=_f(raw.get("gapAverage")),
            gap_distance=_f(raw.get("gapDistance")),
            from_start_ex=_f(raw.get("fromStartEx")),
            to_finish_ex=_f(raw.get("toFinishEx")),
            gap_ex=_f(raw.get("gapEx")),
            gap_chase_ex=_f(raw.get("gapChaseEx")),
            gap_average_ex=_f(raw.get("gapAverageEx")),
            gap_distance_ex=_f(raw.get("gapDistanceEx")),
        )


@dataclass(frozen=True, slots=True)
class ParticipantDevice:
    """Tracker device info for a participant."""

    external_id: str | None
    battery: int | None
    online: bool | None
    is_moving: bool | None
    last_location_gps_fix: bool | None
    last_location_at: datetime | None
    device_id: str | None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Self:
        """Parse the device object."""
        battery = raw.get("battery")
        return cls(
            external_id=raw.get("externalId"),
            battery=int(battery) if battery is not None else None,
            online=raw.get("online"),
            is_moving=raw.get("isMoving"),
            last_location_gps_fix=raw.get("lastLocationGpsFix"),
            last_location_at=_dt(raw.get("lastLocationAt")),
            device_id=raw.get("deviceId"),
        )


@dataclass(frozen=True, slots=True)
class Participant:
    """A race participant (starter)."""

    id: str
    name: str | None
    start_number: str | None
    marker_color: str | None
    tags: dict[str, str]
    current: ParticipantCurrent | None
    device: ParticipantDevice | None

    @property
    def display_name(self) -> str:
        """Human-friendly name."""
        if self.name:
            return self.name
        if self.start_number:
            return f"#{self.start_number}"
        return self.id

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Self:
        """Parse a starter object. Raises KeyError if id is missing."""
        current = raw.get("current")
        device = raw.get("device")
        return cls(
            id=raw["id"],
            name=raw.get("name"),
            start_number=raw.get("startNumber"),
            marker_color=raw.get("markerColor"),
            tags=dict(raw.get("tags") or {}),
            current=ParticipantCurrent.parse(current) if current else None,
            device=ParticipantDevice.parse(device) if device else None,
        )


@dataclass(frozen=True, slots=True)
class EventInfo:
    """Event-level metadata."""

    name: str | None
    location: str | None
    start_time: datetime | None
    end_time: datetime | None
    result_time: datetime | None

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Self:
        """Parse the event object."""
        return cls(
            name=raw.get("name"),
            location=raw.get("location"),
            start_time=_dt(raw.get("startTime")),
            end_time=_dt(raw.get("endTime")),
            result_time=_dt(raw.get("resultTime")),
        )


@dataclass(frozen=True, slots=True)
class RaceData:
    """Full parsed /current payload."""

    event: EventInfo
    participants: tuple[Participant, ...]

    @property
    def participants_by_id(self) -> dict[str, Participant]:
        """Index participants by id."""
        return {p.id: p for p in self.participants}

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> Self:
        """Parse the full payload, skipping malformed starters."""
        participants: list[Participant] = []
        for raw in payload.get("starters") or []:
            try:
                participants.append(Participant.parse(raw))
            except (KeyError, TypeError):
                LOGGER.warning("Skipping malformed participant entry: %s", raw)
        return cls(
            event=EventInfo.parse(payload),
            participants=tuple(participants),
        )
