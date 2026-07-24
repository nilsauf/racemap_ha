"""Base entity and device-info helpers for RaceMap."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator
from .models import EventInfo, Participant


def event_device_info(
    entry: RaceMapConfigEntry, event: EventInfo
) -> DeviceInfo:
    """Build the event device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=event.name or entry.title,
        manufacturer=MANUFACTURER,
        model="Event",
    )


def participant_device_info(
    entry: RaceMapConfigEntry, participant: Participant
) -> DeviceInfo:
    """Build a participant device info."""
    event_id = entry.data["event_id"]
    return DeviceInfo(
        identifiers={(DOMAIN, f"{event_id}_{participant.id}")},
        name=participant.display_name,
        manufacturer=MANUFACTURER,
        model="Participant",
        via_device=(DOMAIN, entry.entry_id),
    )


class RaceMapEntity(CoordinatorEntity[RaceMapDataUpdateCoordinator]):
    """Base class for RaceMap entities."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
