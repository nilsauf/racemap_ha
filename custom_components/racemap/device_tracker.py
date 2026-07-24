"""Device tracker platform for RaceMap."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_EVENT_ID
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator
from .entity import RaceMapEntity, participant_device_info
from .models import Participant
from .sensor import selected_participants

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RaceMapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RaceMap device trackers."""
    coordinator = entry.runtime_data
    known_participant_ids: set[str] = set()

    @callback
    def _add_trackers() -> None:
        """Add trackers for selected participants in coordinator data."""
        new_entities: list[RaceMapDeviceTracker] = []
        for participant in selected_participants(entry, coordinator.data):
            if participant.id in known_participant_ids:
                continue
            known_participant_ids.add(participant.id)
            new_entities.append(RaceMapDeviceTracker(coordinator, entry, participant.id))
        if new_entities:
            async_add_entities(new_entities)

    _add_trackers()
    entry.async_on_unload(coordinator.async_add_listener(_add_trackers))


class RaceMapDeviceTracker(RaceMapEntity, TrackerEntity):
    """GPS tracker for a participant."""

    _attr_name = None
    _attr_source_type = SourceType.GPS

    def __init__(
        self,
        coordinator: RaceMapDataUpdateCoordinator,
        entry: RaceMapConfigEntry,
        participant_id: str,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._participant_id = participant_id
        event_id = entry.data[CONF_EVENT_ID]
        self._attr_unique_id = f"{event_id}_{participant_id}_tracker"
        participant = coordinator.data.participants_by_id[participant_id]
        self._attr_device_info = participant_device_info(entry, participant)

    @property
    def _participant(self) -> Participant | None:
        """Return the participant in the latest coordinator data."""
        return self.coordinator.data.participants_by_id.get(self._participant_id)

    @property
    def available(self) -> bool:
        """Return whether the participant has a current GPS location."""
        participant = self._participant
        if not super().available or participant is None:
            return False
        current = participant.current
        return current is not None and current.lat is not None and current.lng is not None

    @property
    def latitude(self) -> float | None:
        """Return the participant's current latitude."""
        participant = self._participant
        if participant is None or participant.current is None:
            return None
        return participant.current.lat

    @property
    def longitude(self) -> float | None:
        """Return the participant's current longitude."""
        participant = self._participant
        if participant is None or participant.current is None:
            return None
        return participant.current.lng
