<p align="center">
  <img src="custom_components/racemap/brand/logo.png" alt="RaceMap" width="320">
</p>

# RaceMap for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration that
connects a [RaceMap](https://racemap.com/) event to your smart home. It polls
RaceMap's live geodata API and exposes event metadata, per-participant timing
and location metrics, and GPS trackers as Home Assistant devices and entities.

Built against the RaceMap [live geodata API](https://docs.racemap.com/api) and
its [`/current` endpoint](https://docs.racemap.com/api/current.md).

## What it adds to Home Assistant

- **One event device** for the configured RaceMap event, with sensors for
  event location, start time, end time, result time, and participant count.
- **A participant device** for each participant you select, with sensors for
  the timing and location metrics RaceMap reports (see
  [Features](#features)).
- **A `device_tracker` entity** per selected participant, using their latest
  GPS coordinates, so participants appear on the Home Assistant map.
- **Diagnostic entities** (battery, last-location time, connection state) when
  RaceMap provides tracker-device metadata for a participant.

All entities for an entry share a single data-update coordinator that polls the
RaceMap `/current` endpoint at your configured interval.

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

You need two values before setup:

- A RaceMap **API token**.
- The **event ID** of the RaceMap event to monitor.

> The event's API module must be active. RaceMap
> [auto-pauses API access](https://docs.racemap.com/api/auto-pausation.md) two
> hours after an event ends; re-enable it in your event settings if requests
> are rejected.

### How to obtain the API token

1. Sign in at [racemap.com/auth/login](https://racemap.com/auth/login).
2. Open your [account settings](https://racemap.com/admin/account).
3. In the **API Tokens** section, click **Add Token** and copy the generated
   token.

The token is shown only once — copy it before leaving the page. See the
RaceMap [authentication docs](https://docs.racemap.com/api/authentication.md)
for details. The integration sends this token as a Bearer token on every
request.

### How to find the event ID

The event ID is the `:eventId` segment in RaceMap URLs, for example the
`/current` endpoint path:

```
https://racemap.com/api/data/v1/:eventId/current
```

Open the event in RaceMap and copy the `eventId` from its URL. The same ID
appears in event deep links such as `https://racemap.app/events/:eventId`.

## Configuration

The setup dialog requests:

- **API token** — your RaceMap API token.
- **Event ID** — the RaceMap event identifier.

The integration validates both by fetching the event's current data before
creating the entry.

After setup, open **Configure** on the integration to set:

- **Update interval** — polling interval in seconds (minimum 5, default 30).
- **Participants** — the event participants to expose as devices and entities.

You can update the token or event ID later via **Reconfigure**, and Home
Assistant prompts for a new token via **Reauthenticate** if the token becomes
invalid.

## Features

Each selected participant creates sensors for the metrics RaceMap provides,
including: speed, distance from start, distance to finish, gap distance, ETA,
gap, gap chase, average gap, distance to track, elevation, latitude, longitude,
current time, and — when tracker-device metadata is available — battery, last
location time, and connection state.

RaceMap also publishes **extrapolated** variants of the distance and gap
metrics (distance from start, distance to finish, gap, gap distance, gap chase,
and average gap). These sensors are created but **disabled by default** — enable
them per entity if you want RaceMap's projected values alongside the measured
ones.

Selected participants also get a `device_tracker` entity with their latest GPS
coordinates. 

When a participant is deselected or leaves the event, the
integration removes only its own config-entry association from the participant
device; Home Assistant then handles orphan cleanup once no config entries
reference the device.

## Supported

- One Home Assistant event device for the configured RaceMap event.
- Participant devices for the participants you select.
- A `device_tracker` entity per selected participant when RaceMap provides
  current GPS coordinates.
- Diagnostic entities (battery, connection state) when RaceMap provides
  tracker-device metadata.

## Not supported

- Automatic discovery of RaceMap events or devices.
- GPS tracker or diagnostic entities when RaceMap provides no current location
  or device metadata for a participant.

## Limitations

- Shadowtrack-dependent fields — including distance to track and some gap
  values — are `null` when the event has no mapped track.
- RaceMap does not push updates or provide webhooks; this integration polls.
- Each integration entry monitors exactly one event.

## Troubleshooting

- Reauthenticate the integration if the API token is invalid or has changed.
- Confirm the event ID identifies an event accessible to the token.
- If requests fail after an event, check whether API access was
  [auto-paused](https://docs.racemap.com/api/auto-pausation.md).
- Enable debug logging for `custom_components.racemap` to inspect API and
  coordinator update problems.

## Removal

Remove the RaceMap integration entry from **Settings > Devices & services**,
then restart Home Assistant if entities remain displayed. For a manual install,
remove `custom_components/racemap` from the configuration directory as well.
