# Immediate Participant Device Cleanup

## Goal

Remove RaceMap participant devices when they are deselected through the RaceMap
options flow, without removing the event device or unrelated devices.

## Design

Device cleanup belongs to the options-flow lifecycle rather than the sensor
platform or a config-entry update listener. Move the stale-device cleanup
helper from `sensor.py` to an integration-level device helper that accepts the
proposed participant IDs explicitly.

`RaceMapOptionsFlow` continues to extend `OptionsFlowWithReload`. When a user
submits options, `async_step_init` invokes cleanup with
`user_input[CONF_PARTICIPANTS]` before returning `async_create_entry`. The
framework then persists the options and performs its existing automatic reload.

This avoids config-entry update listeners, which Home Assistant expressly
disallows for entries managed by `OptionsFlowWithReload`. Arbitrary direct
calls to `async_update_entry` intentionally do not initiate device cleanup.

The helper removes only device registry entries that:

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
not refresh coordinator data or call the RaceMap API, so saving options is not
delayed or coupled to network availability.

## Tests

The dynamic-device test submits the actual options flow, then waits for pending
Home Assistant tasks. It verifies that the deselected participant device is
removed and that the selected participant, event device, and a foreign device
remain registered. The existing options-flow test continues to verify the
automatic reload path accepts the submitted settings.
