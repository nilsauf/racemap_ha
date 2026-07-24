# Design Spec: RaceMap Home Assistant Custom Integration

- **Date:** 2026-07-24
- **Status:** Approved (design)
- **Target quality:** Home Assistant Integration Quality Scale **Silver** fully; **Gold** where feasible for a custom integration.

---

## 1. Purpose

A Home Assistant custom integration for [RaceMap](https://racemap.com) that polls live race data for a single event and exposes it as Home Assistant entities:

- One **event device** with race-level sensors.
- One **participant device** per user-selected starter, with per-participant sensors and a GPS `device_tracker`.

The integration must feel like a first-party HA integration: UI config flow, `DataUpdateCoordinator`-based polling, full typing, async I/O with `aiohttp`, translations, diagnostics, and a test suite ≥95% coverage.

---

## 2. Grounding: the real RaceMap API

Authoritative sources:
- API endpoint: `https://docs.racemap.com/api/current` — `GET https://racemap.com/api/data/v1/{eventId}/current`
- Auth: `https://docs.racemap.com/api/authentication` — `Authorization: Bearer <API_TOKEN>` (required for `/current`).

### 2.1 Request

```
GET https://racemap.com/api/data/v1/{event_id}/current
Authorization: Bearer <token>
```

Single poll returns everything (event + all starters). No second endpoint is required.

### 2.2 Response shape (fields actually returned)

**Event object:** `name`, `location`, `startTime` (UTC ISO), `endTime` (UTC ISO), `resultTime` (UTC ISO), `shadowTrackUrl`, `starters[]`.

**Participant (starter) object:** `id`, `name` (single string), `startNumber`, `markerColor`, `tags` (free-form dict, e.g. `{"Age":"30","Class":"Women","Status":"DSQ"}`), `importId`, `current` (nullable object), `device` (nullable object).

**`current` object** (values are `null` when no location exists in the event window; `*`-marked fields require a shadowtrack and are `null` otherwise):
`time` (UTC), `lat`, `lng`, `elv`, `speed` (m/s), `distanceToShadowTrack` (m), `lngSt`/`latSt` `*`, `speedSt` `*` (m/s), `elvSt` `*` (m), `fromStart` `*` (m), `toFinish` `*` (m), `eta` `*` (s), `gapCalcTime` `*`, `gapDistance` `*` (m), `gap` `*` (s), `gapChase` `*` (s), `gapAverage` `*` (s), plus extrapolated `*Ex` variants (`fromStartEx`, `toFinishEx`, `lngStEx`, `latStEx`, `gapDistanceEx`, `gapEx`, `gapChaseEx`, `gapAverageEx`).

**`device` object** (nullable — `null` when not in tracker management):
`externalId`, `battery` (%), `online` (bool), `isMoving` (bool|null, Queclink only), `lastLocationGpsFix` (bool), `lastLocationAt` (UTC), `deviceId`.

### 2.3 Error behavior (documented + defensive)

Docs confirm invalid/missing token → request rejected; exact status codes for auth/rate-limit are **not** documented. The integration therefore treats defensively:
- `401` / `403` → auth failure → reauth.
- `429` → rate limited → backoff (honor `Retry-After` header if present).
- Other non-2xx / network / timeout → transient update failure.
- `404` (unknown event) → surfaced as `event_not_found` in the config flow; at runtime treated as update failure (event may be temporarily gone).

---

## 3. Design decisions grounded in the real API

The following decisions reconcile early requirement ideas with what the RaceMap API actually returns. The guiding rule: expose **only direct API fields** (no client-side derivation).

| Topic | API reality | Decision |
|---|---|---|
| Authentication | `Authorization: Bearer <token>` required | Config field = **API token**; reauth on 401/403. |
| Participant name | `name` is a single string | Device/entity name = `name`, fallback `startNumber`. |
| Units | API returns **m/s** and **meters** | Store **native** (m/s, m) with device classes; HA converts for display. |
| Race status / phase | No such field | Not implemented. |
| Finisher / active-participant counts | No such field | Not implemented. |
| Overall / class placement | No such field | Not implemented. |
| Leader / leaderboard | No endpoint/field | Not implemented; data model = `event` + `participants` only. |
| Heading | No such field | Not implemented. |
| Heartbeat | No such field | Not implemented. |
| Time gap to leader | Partially exists as `gap`/`gapChase`/`gapAverage` | Mapped as **gap duration sensors** (as-is, not "to leader" computed). |

---

## 4. Architecture

```
custom_components/racemap/
  __init__.py          # async_setup_entry/async_unload_entry, PLATFORMS, runtime_data
  manifest.json        # domain, config_flow, iot_class, codeowners, quality_scale, loggers
  const.py             # DOMAIN, CONF_*, defaults, LOGGER, attribution
  api.py               # RaceMapApiClient + typed models + exceptions
  coordinator.py       # RaceMapDataUpdateCoordinator[RaceData]
  config_flow.py       # user + reauth + reauth_confirm + reconfigure + OptionsFlow
  entity.py            # RaceMapEntity base + device-info helpers
  sensor.py            # SensorEntityDescription tables (event + participant)
  device_tracker.py    # RaceMapDeviceTracker (TrackerEntity) per participant
  diagnostics.py       # async_get_config_entry_diagnostics (token redacted)
  quality_scale.yaml   # rule tracking
  icons.json           # icon translations
  strings.json         # source translations (config/options/errors/exceptions/entities)
  translations/
    en.json
    de.json
tests/
  __init__.py
  conftest.py          # fixtures: mock config entry, mock client, aiohttp mock
  fixtures/current.json# real /current sample response
  test_init.py
  test_api.py
  test_config_flow.py
  test_coordinator.py
  test_sensor.py
  test_device_tracker.py
  test_diagnostics.py
```

**Data flow:** `aiohttp` session → `RaceMapApiClient.async_get_current()` → `RaceData` → `RaceMapDataUpdateCoordinator` (single poll) → `entry.runtime_data` → all entities read `coordinator.data` only. No entity performs I/O.

**HA-guideline specifics baked in (verified against current docs):**
- Injected websession via `async_get_clientsession` (Platinum `inject-websession`, `async-dependency`).
- `type RaceMapConfigEntry = ConfigEntry[RaceMapDataUpdateCoordinator]`; coordinator stored in `entry.runtime_data` (Bronze `runtime-data`).
- Coordinator: `config_entry=` passed to `super().__init__`; `always_update=False` (RaceData supports `__eq__`); `asyncio.TimeoutError`/`aiohttp.ClientError` left to base coordinator; `UpdateFailed(retry_after=...)` for rate limiting.
- Exceptions: `ConfigEntryNotReady` (first refresh fail), `ConfigEntryAuthFailed` (auth → reauth), `UpdateFailed` (transient).
- `has_entity_name = True` everywhere; entity name = data point only; device name via `DeviceInfo`.
- Entity descriptions: `@dataclass(kw_only=True)` extending `SensorEntityDescription`, with `value_fn`, `exists_fn`, `available_fn`.
- `PARALLEL_UPDATES = 0` in each platform (Silver `parallel-updates`; data comes from coordinator).
- Icon translations in `icons.json` (Gold `icon-translations`), not `icon=` in code.
- Entity name translations via `translation_key` (Gold `entity-translations`).
- Noisy/less-popular entities `entity_registry_enabled_default = False` (Gold `entity-disabled-by-default`).
- Options flow via `OptionsFlowWithReload` (auto-reload on change).

---

## 5. API layer (`api.py`)

### 5.1 Client

```python
class RaceMapApiClient:
    def __init__(self, session: aiohttp.ClientSession, token: str, event_id: str) -> None: ...
    async def async_get_current(self) -> RaceData: ...
```

- Base URL constant in `const.py`; endpoint `f"{BASE_URL}/api/data/v1/{event_id}/current"`.
- Header `Authorization: Bearer {token}`.
- `async with asyncio.timeout(REQUEST_TIMEOUT)` (10 s).
- Status handling: `401/403 → RaceMapAuthError`; `429 → RaceMapRateLimitError(retry_after)`; `404 → RaceMapEventNotFoundError`; other non-2xx → `RaceMapConnectionError`; `aiohttp.ClientError`/timeout → `RaceMapConnectionError`.
- `raise_for_status` avoided in favor of explicit status mapping.
- Structured DEBUG logging: request URL (token never logged), response duration, participant count. INFO on event first-load. No `print()`.

### 5.2 Typed models (frozen dataclasses, `slots=True`, full `__eq__` for `always_update=False`)

```python
@dataclass(frozen=True, slots=True)
class ParticipantCurrent:  # all fields X | None
    time: datetime | None
    lat: float | None
    lng: float | None
    elv: float | None
    speed: float | None                 # m/s
    distance_to_shadow_track: float | None
    speed_st: float | None
    elv_st: float | None
    from_start: float | None
    to_finish: float | None
    eta: float | None                   # seconds
    gap: float | None                   # seconds
    gap_chase: float | None
    gap_average: float | None
    gap_distance: float | None
    # extrapolated
    from_start_ex: float | None
    to_finish_ex: float | None
    gap_ex: float | None
    gap_chase_ex: float | None
    gap_average_ex: float | None
    gap_distance_ex: float | None

@dataclass(frozen=True, slots=True)
class ParticipantDevice:
    external_id: str | None
    battery: int | None
    online: bool | None
    is_moving: bool | None
    last_location_gps_fix: bool | None
    last_location_at: datetime | None
    device_id: str | None

@dataclass(frozen=True, slots=True)
class Participant:
    id: str
    name: str | None
    start_number: str | None
    marker_color: str | None
    tags: dict[str, str]
    current: ParticipantCurrent | None
    device: ParticipantDevice | None
    @property
    def display_name(self) -> str: ...  # name or f"#{start_number}" or id

@dataclass(frozen=True, slots=True)
class EventInfo:
    name: str | None
    location: str | None
    start_time: datetime | None
    end_time: datetime | None
    result_time: datetime | None

@dataclass(frozen=True, slots=True)
class RaceData:
    event: EventInfo
    participants: tuple[Participant, ...]
    @property
    def participants_by_id(self) -> Mapping[str, Participant]: ...
```

Parsing is defensive: missing keys → `None`; ISO timestamps via `homeassistant.util.dt.parse_datetime`; malformed participant entries are skipped with a WARNING (plan requirement "ungültige Teilnehmer ignorieren").

### 5.3 Exceptions

```python
class RaceMapError(HomeAssistantError): ...
class RaceMapAuthError(RaceMapError): ...
class RaceMapConnectionError(RaceMapError): ...
class RaceMapEventNotFoundError(RaceMapError): ...
class RaceMapRateLimitError(RaceMapError):
    def __init__(self, retry_after: float | None = None) -> None: ...
```

All raised with translatable messages (`translation_domain=DOMAIN`, `translation_key=...`) for Gold `exception-translations`.

---

## 6. Coordinator (`coordinator.py`)

```python
type RaceMapConfigEntry = ConfigEntry[RaceMapDataUpdateCoordinator]

class RaceMapDataUpdateCoordinator(DataUpdateCoordinator[RaceData]):
    def __init__(self, hass, entry: RaceMapConfigEntry, client: RaceMapApiClient) -> None:
        super().__init__(
            hass, LOGGER, name=DOMAIN, config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> RaceData:
        try:
            return await self.client.async_get_current()
        except RaceMapAuthError as err:
            raise ConfigEntryAuthFailed(...) from err
        except RaceMapRateLimitError as err:
            raise UpdateFailed(...) from err  # with retry_after when available
        except RaceMapError as err:
            raise UpdateFailed(...) from err
```

- Base coordinator handles the "log once when unavailable / once when back" behavior (Silver `log-when-unavailable`).
- No `_async_setup` needed (event metadata comes with each poll).

---

## 7. `__init__.py`

```python
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]

async def async_setup_entry(hass, entry: RaceMapConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = RaceMapApiClient(session, entry.data[CONF_TOKEN], entry.data[CONF_EVENT_ID])
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()  # -> ConfigEntryNotReady / ConfigEntryAuthFailed
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- `test-before-setup` satisfied by `async_config_entry_first_refresh`.
- `config-entry-unloading` satisfied by `async_unload_entry`.
- Options reload handled by `OptionsFlowWithReload` (no manual update listener).

---

## 8. Config / Options flow (`config_flow.py`)

### 8.1 `user` step
- Schema: `token` (`str`, password-styled via selector), `event_id` (`str`). `data_description` for both (Bronze `config-flow` requirement).
- On submit: build a throwaway client → `async_get_current()` (`test-before-configure`).
  - Success → `await async_set_unique_id(event_id)` → `_abort_if_unique_id_configured()` (Bronze `unique-config-entry`) → `async_create_entry(title=event.name or event_id, data={token, event_id})`.
  - `RaceMapAuthError` → error `invalid_auth`.
  - `RaceMapEventNotFoundError` → error `event_not_found`.
  - `RaceMapConnectionError`/`RaceMapRateLimitError` → error `cannot_connect`.
  - unexpected → error `unknown` (logged with `exception`).

### 8.2 `reauth` + `reauth_confirm`
- `async_step_reauth(entry_data)` → `async_step_reauth_confirm`.
- Confirm form asks for a new `token`; validates via `async_get_current()`.
- `await async_set_unique_id(event_id)`, `_abort_if_unique_id_mismatch()`, `return async_update_reload_and_abort(self._get_reauth_entry(), data_updates={CONF_TOKEN: token})`.
- (Silver `reauthentication-flow`.)

### 8.3 `reconfigure` (Gold `reconfiguration-flow`)
- Allows changing `token` and/or `event_id`. Validates via `async_get_current()`; `_abort_if_unique_id_mismatch()` when the event_id changes to an already-configured event; `async_update_reload_and_abort`.

### 8.4 Options flow — `OptionsFlowHandler(OptionsFlowWithReload)`
- Single `init` step, schema built with `add_suggested_values_to_schema(..., self.config_entry.options)`:
  - `CONF_UPDATE_INTERVAL`: `NumberSelector` (min 5, default 30, unit seconds) → satisfies plan "freie Eingabe, Standard 30 s"; min 5 honors HA guidance.
  - `CONF_PARTICIPANTS`: `SelectSelector(multiple=True)` whose options come from the **current** `coordinator.data.participants` (label `display_name` + `#startNumber`, value `id`). If the coordinator has no data yet, fall back to the stored selection.
- Selection persisted in `entry.options`; `OptionsFlowWithReload` triggers reload → platforms rebuild devices/entities.

`async_get_options_flow` returns the handler.

---

## 9. Entities

### 9.1 Base (`entity.py`)

```python
class RaceMapEntity(CoordinatorEntity[RaceMapDataUpdateCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = "Data provided by RaceMap"
```

- `event_device_info(entry, event) -> DeviceInfo`:
  identifiers `{(DOMAIN, entry.entry_id)}` (or `{(DOMAIN, f"event_{event_id}")}`), name = event name, manufacturer "RaceMap", model "Event", `entry_type`/config URL to the RaceMap player.
- `participant_device_info(event_id, participant) -> DeviceInfo`:
  identifiers `{(DOMAIN, f"{event_id}_{participant.id}")}`, name = `participant.display_name`, manufacturer "RaceMap", model "Participant", `via_device` = event device. Stable across restarts (Gold `devices`).

### 9.2 Sensor platform (`sensor.py`)

Entity description dataclass:

```python
@dataclass(frozen=True, kw_only=True)
class RaceMapEventSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EventInfo], StateType | datetime]

@dataclass(frozen=True, kw_only=True)
class RaceMapParticipantSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Participant], StateType | datetime | None]
    exists_fn: Callable[[Participant], bool] = lambda _: True   # e.g. device present
```

**Event sensors** (attached to event device; `translation_key` per row):

| key | device_class | state_class | unit | notes |
|---|---|---|---|---|
| `event_location` | — | — | — | text |
| `start_time` | timestamp | — | — | |
| `end_time` | timestamp | — | — | |
| `result_time` | timestamp | — | — | "last update" |
| `participant_count` | — | measurement | — | `len(participants)` (a count, not a race "status") |

(Event *name* is the device name, not a separate sensor.)

**Participant sensors** (attached to participant device):

| key | device_class | state_class | native unit | enabled_default | category |
|---|---|---|---|---|---|
| `speed` | speed | measurement | m/s | true | — |
| `distance_to_shadow_track` | distance | measurement | m | false | — |
| `from_start` | distance | total | m | true | — |
| `to_finish` | distance | measurement | m | true | — |
| `eta` | duration | measurement | s | true | — |
| `gap` | duration | measurement | s | true | — |
| `gap_chase` | duration | measurement | s | false | — |
| `gap_average` | duration | measurement | s | false | — |
| `gap_distance` | distance | measurement | m | true | — |
| `elevation` | distance | measurement | m | false | — |
| `current_time` | timestamp | — | — | true | diagnostic |
| `latitude` | — | measurement | ° | **false** | — |
| `longitude` | — | measurement | ° | **false** | — |
| `from_start_ex`,`to_finish_ex`,`gap_ex`,`gap_chase_ex`,`gap_average_ex`,`gap_distance_ex` | as base | as base | as base | **false** | — |

**Participant diagnostic sensors** (`EntityCategory.DIAGNOSTIC`, `exists_fn = lambda p: p.device is not None`):

| key | device_class | native unit | enabled_default |
|---|---|---|---|
| `battery` | battery | % | true |
| `last_location_at` | timestamp | — | true |
| `online` | enum (`connected`/`disconnected`) | — | true |

The `online` sensor is an **enum** sensor (`device_class = SensorDeviceClass.ENUM`, `options = ["connected", "disconnected"]`, `value_fn` maps the bool). A `binary_sensor` connectivity variant is deferred to a future platform (see §14).

- `native_value` computed from `value_fn`; returns `None` → entity `unavailable` when the underlying `current`/`device`/field is `None` (Silver `entity-unavailable`).
- `unique_id = f"{event_id}_{participant.id}_{description.key}"` (event sensors: `f"{entry_id}_{description.key}"`).
- `PARALLEL_UPDATES = 0`.

### 9.3 Device tracker (`device_tracker.py`)

```python
class RaceMapDeviceTracker(RaceMapEntity, TrackerEntity):
    _attr_name = None                 # primary location feature of the participant device
    _attr_source_type = SourceType.GPS
```

- One per selected participant; attached to the participant device (same identifiers).
- `unique_id = f"{event_id}_{participant.id}_tracker"`.
- `latitude` → `participant.current.lat`; `longitude` → `participant.current.lng` (memory-only reads).
- `location_accuracy` → default `0` (API exposes no GPS accuracy field).
- `available` → `False` when participant `current` is `None` or `lat`/`lng` are `None`.
- Produces `home`/`not_home`/zone state automatically and places the participant on the HA map.
- `PARALLEL_UPDATES = 0`.

### 9.4 Dynamic devices / stale cleanup (Gold `dynamic-devices`, `stale-devices`)
- Both platforms build entities from `entry.options[CONF_PARTICIPANTS]` ∩ `coordinator.data.participants_by_id`.
- On options reload, newly selected participants get devices/entities; deselected participants' devices are removed via the device registry (participants no longer in the selection or no longer in the event).

---

## 10. Diagnostics (`diagnostics.py`)

```python
TO_REDACT = {CONF_TOKEN, "token", "Authorization"}

async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {"data": async_redact_data(entry.data, TO_REDACT),
                  "options": entry.options},
        "data": <serialized coordinator.data>,   # event + participants, technical only
    }
```

- Token/Authorization always redacted (plan: remove API keys/tokens/passwords).
- Participant names, start numbers, positions are **public race data** and are exported as technical info (plan: "nur technische Informationen").
- Gold `diagnostics`.

---

## 11. Internationalization

- `strings.json` is the source of truth; `translations/en.json` and `translations/de.json` derive from it.
- Covers: `config` (steps `user`, `reauth_confirm`, `reconfigure`; `data`, `data_description`; `error` keys `cannot_connect`/`invalid_auth`/`event_not_found`/`unknown`; `abort` keys `already_configured`/`reauth_successful`/`reconfigure_successful`), `options` (step `init` fields + descriptions), `entity` (translated names + states for every sensor `translation_key` and the tracker), `exceptions` (translatable messages for each `RaceMapError` subclass).
- `icons.json` provides icon translations per `translation_key`:
  - `speed` → `mdi:speedometer`
  - `from_start`/`to_finish`/`gap_distance`/`distance_to_shadow_track` → `mdi:map-marker-distance`
  - `eta`/`gap`/`gap_chase`/`gap_average` → `mdi:timer-outline`
  - `participant_count` → `mdi:account-group`
  - `online` → state icons `mdi:lan-connect` / `mdi:lan-disconnect`
  - `battery` handled by device_class default.
- No hard-coded natural-language strings in Python (plan: "keine festen Strings").

---

## 12. Manifest & quality tracking

`manifest.json`:
```json
{
  "domain": "racemap",
  "name": "RaceMap",
  "codeowners": ["@<owner>"],
  "config_flow": true,
  "documentation": "https://github.com/<owner>/racemap-ha",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/<owner>/racemap-ha/issues",
  "loggers": ["custom_components.racemap"],
  "quality_scale": "silver",
  "requirements": [],
  "version": "0.1.0"
}
```
- Self-contained `api.py` → no third-party `requirements` (dependency transparency trivially satisfied).

`quality_scale.yaml`: every Bronze + Silver rule marked `done`; Gold rules marked `done` where met (`devices`, `diagnostics`, `entity-category`, `entity-device-class`, `entity-disabled-by-default`, `entity-translations`, `exception-translations`, `icon-translations`, `reconfiguration-flow`, `dynamic-devices`, `stale-devices`, docs rules) and `exempt` with reason where not (`discovery`, `discovery-update-info` → cloud service, no network discovery; `repair-issues` → no user-actionable repairs beyond reauth; Platinum `strict-typing` targeted but declared per final mypy result).

---

## 13. Testing (`tests/`, target ≥95% — Silver `test-coverage`, Bronze `config-flow-test-coverage`)

Framework: `pytest-homeassistant-custom-component`. Real `/current` sample stored as `tests/fixtures/current.json`.

- `conftest.py`: `MockConfigEntry` factory, `mock_racemap_client` (AsyncMock returning parsed `RaceData` from fixture), aiohttp response mocking for `api.py` tests, `enable_custom_integrations` fixture.
- `test_api.py`: URL/header construction; success parse from fixture; 401→`RaceMapAuthError`, 403→auth, 429→`RaceMapRateLimitError`(+retry_after), 404→`RaceMapEventNotFoundError`, 5xx/network/timeout→`RaceMapConnectionError`; malformed participant skipped; token never logged.
- `test_config_flow.py`: user success; each error path; `unique-config-entry` abort; reauth success + `unique_id` mismatch abort; reconfigure success; options flow (interval + participant multiselect, suggested values).
- `test_coordinator.py`: success; auth→`ConfigEntryAuthFailed`; rate limit→`UpdateFailed`; connection→`UpdateFailed`; `always_update=False` no-change dedupe.
- `test_init.py`: setup + forward platforms; `ConfigEntryNotReady` on first-refresh failure; unload.
- `test_sensor.py`: value_fn correctness per description; `None` field → `unavailable`; diagnostic `exists_fn` (no device → not created); disabled-by-default flags; dynamic add/remove on option change.
- `test_device_tracker.py`: coordinates present → lat/lng + state; `current` null → unavailable; source_type GPS; dynamic add/remove.
- `test_diagnostics.py`: token redacted; technical data present.

Verification commands (must pass before completion): `ruff check .`, `ruff format --check .`, `mypy custom_components/racemap`, `pytest --cov=custom_components/racemap --cov-report=term-missing` (≥95%).

---

## 14. Extensibility (future, no rearchitecture)

- `api.py` client can grow methods for `/starters`, `/ranks`, `/times`, `/unified`, shadowtrack GeoJSON, and query params (`avgSpeedWindow`, `participantId`, `resultTime`) without touching entities.
- New platforms (`binary_sensor` for `online`/`isMoving`, `geo_location`, `number` for `avgSpeedWindow`, `calendar`/`event`) plug in by appending to `PLATFORMS` and adding a module; coordinator/data model already carry the data.
- Reference-participant gap calculations available by passing `participantId` — future option.

---

## 15. Out of scope (explicitly)

- Derived leaderboard/placement/status/finisher/leader logic (user chose direct fields only).
- Push/webhook (`/current` is poll-only here).
- Multiple events per config entry (one event per entry; multiple entries allowed).
- Unit conversion in code (HA handles display units from native m/s and m).
