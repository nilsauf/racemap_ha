# RaceMap for Home Assistant

RaceMap connects a RaceMap event to Home Assistant. It exposes event metadata,
selected participant timing and location data, and participant GPS trackers.

## Installation

### HACS

1. Add this repository as a custom repository in HACS with the **Integration**
   category.
2. Install **RaceMap** from HACS.
3. Restart Home Assistant.
4. Add **RaceMap** from **Settings > Devices & services > Add integration**.

### Manual

1. Copy `custom_components/racemap` into your Home Assistant
   `config/custom_components` directory.
2. Restart Home Assistant.
3. Add **RaceMap** from **Settings > Devices & services > Add integration**.

## Prerequisites

You need a RaceMap API token and the ID of the RaceMap event to monitor.

## Configuration

The integration setup requests these parameters:

- **API token**: your RaceMap API token.
- **Event ID**: the RaceMap event identifier.

After setup, open **Configure** for the integration to set these options:

- **Update interval**: polling interval in seconds.
- **Participants**: the event participants to expose as devices and entities.

## Functionality

Each entry creates an event device with location, start time, end time, result
time, and participant-count sensors. Each selected participant creates a
participant device with sensors for speed, distance from start, distance to
finish, gap distance, ETA, gap, gap chase, average gap, distance to track,
elevation, latitude, longitude, current time, battery, last location, and
connection state when the RaceMap data provides them.

RaceMap also publishes extrapolated variants of the distance and gap metrics
(distance from start, distance to finish, gap, gap distance, gap chase, and
average gap). Those extrapolated sensors are created but disabled by default;
enable them per entity if you want RaceMap's projected values in addition to
the measured ones.

Selected participants also create a `device_tracker` entity with their latest
GPS coordinates. When a participant is deselected or disappears from the event,
the integration safely removes only its own config-entry association from the
participant device. Home Assistant then owns orphan cleanup and removes the
device once no config entries reference it.

RaceMap polls the API's `/current` endpoint through a data-update coordinator
every configured number of seconds. All entities for an entry use that shared
refresh result.

## Limitations

- Shadowtrack-dependent fields, including distance to track and some gap
  values, are `null` when the event has no mapped track.
- RaceMap does not provide push or webhook updates; this integration polls.
- Each integration entry monitors one event.

## Troubleshooting

- Reauthenticate the integration if the API token is invalid or has changed.
- Confirm that the event ID identifies an event accessible to the token.
- Enable debug logging for `custom_components.racemap` to inspect API and
  coordinator update problems.

## Removal

Remove the RaceMap integration entry from **Settings > Devices & services**,
then restart Home Assistant if entities remain displayed. For a manual install,
remove `custom_components/racemap` from the configuration directory as well.

## Example Automation

Notify when a participant's gap drops below 60 seconds:

```yaml
alias: RaceMap participant closes the gap
triggers:
  - trigger: numeric_state
    entity_id: sensor.alice_anderson_gap
    below: 60
conditions: []
actions:
  - action: notify.mobile_app_phone
    data:
      message: Alice is now less than one minute behind.
mode: single
```
