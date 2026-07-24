# Immediate Participant Device Cleanup

## Goal

Remove RaceMap participant devices immediately after they are deselected in a
config entry's options, without removing the event device or unrelated devices.

## Design

Device cleanup belongs to the integration lifecycle rather than the sensor
platform. Move the stale-device cleanup helper from `sensor.py` to the
integration module (or an integration-level device helper).

During `async_setup_entry`, register a config-entry update listener with
`entry.add_update_listener`. The listener runs whenever Home Assistant updates
the entry, including direct `async_update_entry` calls and saves through the
options flow.

The listener reads the updated participant selection and removes only device
registry entries that:

- belong to the updated config entry;
- have a RaceMap participant identifier using `<event_id>_<participant_id>`;
- are not included in the updated participant selection.

The cleanup must not remove the event device, selected participant devices, or
unrelated devices attached to the same config entry.

Coordinator listeners remain responsible only for dynamically adding entities
when refreshed race data contains newly selected participants. They do not
perform device cleanup.

## Error Handling

Cleanup operates solely on the local Home Assistant device registry. It does
not refresh coordinator data or call the RaceMap API, so an options update is
not delayed or coupled to network availability.

## Tests

The dynamic-device test updates entry options directly and waits for pending
Home Assistant tasks. It verifies that the deselected participant device is
removed immediately and that the selected participant, event device, and a
foreign device remain registered.
