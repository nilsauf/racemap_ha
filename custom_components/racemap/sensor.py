"""Sensor platform for RaceMap."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_EVENT_ID, CONF_PARTICIPANTS, DOMAIN
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator
from .entity import RaceMapEntity, event_device_info, participant_device_info
from .models import EventInfo, Participant, RaceData

PARALLEL_UPDATES = 0

type EventValueFn = Callable[[EventInfo], StateType | datetime]
type ParticipantValueFn = Callable[[Participant], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class RaceMapEventSensorDescription(SensorEntityDescription):
    """Describe an event sensor."""

    value_fn: EventValueFn


def _participant_exists(_: Participant) -> bool:
    """Return whether a participant sensor should be created."""
    return True


@dataclass(frozen=True, kw_only=True)
class RaceMapParticipantSensorDescription(SensorEntityDescription):
    """Describe a participant sensor."""

    value_fn: ParticipantValueFn
    exists_fn: Callable[[Participant], bool] = _participant_exists


def _current_value(participant: Participant, attribute: str) -> StateType | datetime:
    """Return a live participant value when it is available."""
    if participant.current is None:
        return None
    return getattr(participant.current, attribute)


def _has_device(participant: Participant) -> bool:
    """Return whether the participant has a tracker device."""
    return participant.device is not None


EVENT_SENSORS: tuple[RaceMapEventSensorDescription, ...] = (
    RaceMapEventSensorDescription(
        key="event_location",
        translation_key="event_location",
        value_fn=lambda event: event.location,
    ),
    RaceMapEventSensorDescription(
        key="start_time",
        translation_key="start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda event: event.start_time,
    ),
    RaceMapEventSensorDescription(
        key="end_time",
        translation_key="end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda event: event.end_time,
    ),
    RaceMapEventSensorDescription(
        key="result_time",
        translation_key="result_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda event: event.result_time,
    ),
)

PARTICIPANT_SENSORS: tuple[RaceMapParticipantSensorDescription, ...] = (
    RaceMapParticipantSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        value_fn=lambda participant: _current_value(participant, "speed"),
    ),
    RaceMapParticipantSensorDescription(
        key="from_start",
        translation_key="from_start",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda participant: _current_value(participant, "from_start"),
    ),
    RaceMapParticipantSensorDescription(
        key="from_start_ex",
        translation_key="from_start_ex",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "from_start_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="to_finish",
        translation_key="to_finish",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda participant: _current_value(participant, "to_finish"),
    ),
    RaceMapParticipantSensorDescription(
        key="to_finish_ex",
        translation_key="to_finish_ex",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "to_finish_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_distance",
        translation_key="gap_distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda participant: _current_value(participant, "gap_distance"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_distance_ex",
        translation_key="gap_distance_ex",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_distance_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="eta",
        translation_key="eta",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda participant: _current_value(participant, "eta"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap",
        translation_key="gap",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda participant: _current_value(participant, "gap"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_ex",
        translation_key="gap_ex",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_chase",
        translation_key="gap_chase",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_chase"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_chase_ex",
        translation_key="gap_chase_ex",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_chase_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_average",
        translation_key="gap_average",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_average"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_average_ex",
        translation_key="gap_average_ex",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "gap_average_ex"),
    ),
    RaceMapParticipantSensorDescription(
        key="distance_to_shadow_track",
        translation_key="distance_to_shadow_track",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(
            participant, "distance_to_shadow_track"
        ),
    ),
    RaceMapParticipantSensorDescription(
        key="elevation",
        translation_key="elevation",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "elv"),
    ),
    RaceMapParticipantSensorDescription(
        key="latitude",
        translation_key="latitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "lat"),
    ),
    RaceMapParticipantSensorDescription(
        key="longitude",
        translation_key="longitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        entity_registry_enabled_default=False,
        value_fn=lambda participant: _current_value(participant, "lng"),
    ),
    RaceMapParticipantSensorDescription(
        key="current_time",
        translation_key="current_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda participant: _current_value(participant, "time"),
    ),
)

PARTICIPANT_DIAGNOSTIC_SENSORS: tuple[RaceMapParticipantSensorDescription, ...] = (
    RaceMapParticipantSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_device,
        value_fn=lambda participant: (
            participant.device.battery if participant.device else None
        ),
    ),
    RaceMapParticipantSensorDescription(
        key="last_location_at",
        translation_key="last_location_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_device,
        value_fn=lambda participant: (
            participant.device.last_location_at if participant.device else None
        ),
    ),
    RaceMapParticipantSensorDescription(
        key="online",
        translation_key="online",
        device_class=SensorDeviceClass.ENUM,
        options=["connected", "disconnected"],
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=_has_device,
        value_fn=lambda participant: (
            None
            if participant.device is None or participant.device.online is None
            else "connected"
            if participant.device.online
            else "disconnected"
        ),
    ),
)


def selected_participants(
    entry: RaceMapConfigEntry, data: RaceData
) -> list[Participant]:
    """Return selected participants that exist in refreshed data."""
    participants_by_id = data.participants_by_id
    return [
        participants_by_id[participant_id]
        for participant_id in entry.options.get(CONF_PARTICIPANTS, [])
        if participant_id in participants_by_id
    ]


def _cleanup_stale_devices(
    hass: HomeAssistant, entry: RaceMapConfigEntry, data: RaceData
) -> None:
    """Remove this entry's stale participant device associations."""
    event_id = entry.data[CONF_EVENT_ID]
    selected_ids = set(entry.options.get(CONF_PARTICIPANTS, []))
    retained = {
        (DOMAIN, f"{event_id}_{participant_id}")
        for participant_id in selected_ids & data.participants_by_id.keys()
    }
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        participant_identifiers = {
            identifier
            for identifier in device.identifiers
            if identifier[0] == DOMAIN and identifier[1].startswith(f"{event_id}_")
        }
        if participant_identifiers and not participant_identifiers & retained:
            registry.async_update_device(
                device.id,
                remove_config_entry_id=entry.entry_id,
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RaceMapConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RaceMap sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        RaceMapEventSensor(coordinator, entry, description)
        for description in EVENT_SENSORS
    ]
    entities.append(RaceMapParticipantCountSensor(coordinator, entry))
    known_participant_ids: set[str] = set()

    @callback
    def _add_participant_entities() -> None:
        """Add sensors for selected participants appearing in coordinator data."""
        _cleanup_stale_devices(hass, entry, coordinator.data)
        new_entities: list[SensorEntity] = []
        for participant in selected_participants(entry, coordinator.data):
            if participant.id in known_participant_ids:
                continue
            known_participant_ids.add(participant.id)
            for description in PARTICIPANT_SENSORS + PARTICIPANT_DIAGNOSTIC_SENSORS:
                if description.exists_fn(participant):
                    new_entities.append(
                        RaceMapParticipantSensor(
                            coordinator, entry, participant.id, description
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    async_add_entities(entities)
    _add_participant_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_participant_entities))


class RaceMapEventSensor(RaceMapEntity, SensorEntity):
    """A sensor on the event device."""

    entity_description: RaceMapEventSensorDescription

    def __init__(
        self,
        coordinator: RaceMapDataUpdateCoordinator,
        entry: RaceMapConfigEntry,
        description: RaceMapEventSensorDescription,
    ) -> None:
        """Initialize the event sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = event_device_info(entry, coordinator.data.event)

    @property
    def native_value(self) -> StateType | datetime:
        """Return the value from coordinator data."""
        return self.entity_description.value_fn(self.coordinator.data.event)


class RaceMapParticipantCountSensor(RaceMapEntity, SensorEntity):
    """Number of participants in the event."""

    _attr_translation_key = "participant_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: RaceMapDataUpdateCoordinator,
        entry: RaceMapConfigEntry,
    ) -> None:
        """Initialize the participant count sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_participant_count"
        self._attr_device_info = event_device_info(entry, coordinator.data.event)

    @property
    def native_value(self) -> int:
        """Return the participant count from coordinator data."""
        return len(self.coordinator.data.participants)


class RaceMapParticipantSensor(RaceMapEntity, SensorEntity):
    """A sensor on a participant device."""

    entity_description: RaceMapParticipantSensorDescription

    def __init__(
        self,
        coordinator: RaceMapDataUpdateCoordinator,
        entry: RaceMapConfigEntry,
        participant_id: str,
        description: RaceMapParticipantSensorDescription,
    ) -> None:
        """Initialize the participant sensor."""
        super().__init__(coordinator)
        self._participant_id = participant_id
        self.entity_description = description
        event_id = entry.data[CONF_EVENT_ID]
        self._attr_unique_id = f"{event_id}_{participant_id}_{description.key}"
        participant = coordinator.data.participants_by_id[participant_id]
        self._attr_device_info = participant_device_info(entry, participant)

    @property
    def _participant(self) -> Participant | None:
        """Return the participant in the latest coordinator data."""
        return self.coordinator.data.participants_by_id.get(self._participant_id)

    @property
    def available(self) -> bool:
        """Return whether a current value is available."""
        participant = self._participant
        return (
            super().available
            and participant is not None
            and self.entity_description.value_fn(participant) is not None
        )

    @property
    def native_value(self) -> StateType | datetime:
        """Return the latest participant value from coordinator data."""
        participant = self._participant
        if participant is None:
            return None
        return self.entity_description.value_fn(participant)
