# RaceMap Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Silver/Gold-grade Home Assistant custom integration that polls the RaceMap `/current` API for one event and exposes race + participant data as sensors and per-participant GPS device trackers.

**Architecture:** A single `RaceMapApiClient` (aiohttp, injected websession) fetches one `/current` payload into a frozen typed `RaceData` model. A `DataUpdateCoordinator` polls it and stores itself in `ConfigEntry.runtime_data`. All entities (event sensors, participant sensors, participant `TrackerEntity`) are `CoordinatorEntity` subclasses that read `coordinator.data` only — no entity performs I/O. UI config flow handles setup, reauth, reconfigure; an `OptionsFlowWithReload` handles refresh interval + participant multi-select.

**Tech Stack:** Python 3.13+, Home Assistant Core APIs, `aiohttp`, `voluptuous`, `pytest` + `pytest-homeassistant-custom-component`, `ruff`, `mypy`.

**Design spec:** `docs/superpowers/specs/2026-07-24-racemap-integration-design.md` (read it before starting).

## Global Constraints

- Python 3.13+; full type annotations on every function/method; `from __future__ import annotations` at top of every module.
- Fully async; no blocking I/O; all HTTP via `aiohttp` with `asyncio.timeout`.
- Domain: `racemap`. All code under `custom_components/racemap/`.
- All HTTP goes through `api.py` only. Entities read `coordinator.data` only — never call the API.
- No hard-coded natural-language UI strings in Python; all via `strings.json` / `translations/` / `icons.json`.
- No `print()`; use `LOGGER` from `const.py` (`logging.getLogger(__package__)`). Never log the token.
- API base URL: `https://racemap.com`. Endpoint: `GET /api/data/v1/{event_id}/current`. Auth header: `Authorization: Bearer {token}`.
- Units stored native: speed in `m/s`, distances in `m`, durations in `s`. HA converts for display.
- `has_entity_name = True` on all entities; `PARALLEL_UPDATES = 0` in every platform module.
- Attribution string: `"Data provided by RaceMap"`.
- Device identifiers: event = `(DOMAIN, entry.entry_id)`; participant = `(DOMAIN, f"{event_id}_{participant_id}")`.
- Target: ≥95% test coverage on all modules; `ruff check`, `ruff format --check`, `mypy` clean.
- Commit after every task with a Conventional Commits message.

**Prerequisite (one-time, before Task 1):** create/activate a Python 3.13 venv and install deps:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install homeassistant pytest pytest-homeassistant-custom-component pytest-cov ruff mypy aioresponses
```
Add a `requirements_test.txt` capturing these. This repo is not yet a git repo — run `git init` and make an initial commit of the `docs/` directory before Task 1.

---

### Task 1: Test fixture + constants + package skeleton

**Files:**
- Create: `custom_components/racemap/__init__.py` (empty package marker for now; real content in Task 6)
- Create: `custom_components/racemap/const.py`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/current.json`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `const.DOMAIN: str = "racemap"`
  - `const.LOGGER: logging.Logger`
  - `const.BASE_URL: str = "https://racemap.com"`
  - `const.REQUEST_TIMEOUT: int = 10`
  - `const.CONF_TOKEN = "token"`, `const.CONF_EVENT_ID = "event_id"`, `const.CONF_UPDATE_INTERVAL = "update_interval"`, `const.CONF_PARTICIPANTS = "participants"`
  - `const.DEFAULT_UPDATE_INTERVAL = 30`, `const.MIN_UPDATE_INTERVAL = 5`
  - `const.ATTRIBUTION = "Data provided by RaceMap"`
  - `const.MANUFACTURER = "RaceMap"`
  - conftest fixtures: `current_json` (dict), `enable_custom_integrations` (autouse via pytest-homeassistant-custom-component).

- [ ] **Step 1: Create the package marker and constants**

`custom_components/racemap/__init__.py`:
```python
"""The RaceMap integration."""
```

`custom_components/racemap/const.py`:
```python
"""Constants for the RaceMap integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "racemap"
LOGGER: Final = logging.getLogger(__package__)

BASE_URL: Final = "https://racemap.com"
REQUEST_TIMEOUT: Final = 10

CONF_TOKEN: Final = "token"
CONF_EVENT_ID: Final = "event_id"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_PARTICIPANTS: Final = "participants"

DEFAULT_UPDATE_INTERVAL: Final = 30
MIN_UPDATE_INTERVAL: Final = 5

ATTRIBUTION: Final = "Data provided by RaceMap"
MANUFACTURER: Final = "RaceMap"
```

- [ ] **Step 2: Save the real API sample as a fixture**

Create `tests/fixtures/current.json` with the documented sample response (three starters: one with `device`, one with `device: null`, one DSQ via `tags.Status`). Copy the JSON body verbatim from the design spec §2.2 sample (the `{ "name": "Sample live API | 100km-Duathlon", ... "starters": [...] }` object). Ensure it includes: a starter with a full `current` + `device`, a starter with `device: null`, and a starter whose `tags` contain `"Status": "DSQ"`.

- [ ] **Step 3: Create conftest with base fixtures**

`tests/conftest.py`:
```python
"""Fixtures for RaceMap tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def current_json() -> dict[str, Any]:
    """Return the sample /current API response."""
    path = Path(__file__).parent / "fixtures" / "current.json"
    return json.loads(path.read_text(encoding="utf-8"))
```

`tests/__init__.py`:
```python
"""Tests for the RaceMap integration."""
```

- [ ] **Step 4: Verify the fixture loads**

Run: `pytest tests/ -q` (collects nothing yet but must not error on import). Then in a REPL or a temporary test, assert `current_json["starters"]` has length 3. Expected: no collection errors.

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/__init__.py custom_components/racemap/const.py tests/__init__.py tests/conftest.py tests/fixtures/current.json
git commit -m "feat(racemap): add package skeleton, constants, and test fixtures"
```

---

### Task 2: API models and exceptions

**Files:**
- Create: `custom_components/racemap/models.py`
- Create: `custom_components/racemap/exceptions.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces (exact names/types used by every later task):
  - `exceptions.RaceMapError(HomeAssistantError)`
  - `exceptions.RaceMapAuthError(RaceMapError)`
  - `exceptions.RaceMapConnectionError(RaceMapError)`
  - `exceptions.RaceMapEventNotFoundError(RaceMapError)`
  - `exceptions.RaceMapRateLimitError(RaceMapError)` with `.retry_after: float | None`
  - `models.EventInfo`, `models.ParticipantCurrent`, `models.ParticipantDevice`, `models.Participant`, `models.RaceData` (all frozen `@dataclass(slots=True)`)
  - `Participant.display_name: str` property
  - `RaceData.participants_by_id -> dict[str, Participant]` property
  - `RaceData.parse(payload: dict) -> RaceData` classmethod (defensive parser; skips malformed starters with a WARNING)

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
"""Tests for RaceMap data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from custom_components.racemap.models import Participant, RaceData


def test_parse_full_payload(current_json: dict[str, Any]) -> None:
    data = RaceData.parse(current_json)
    assert data.event.name == current_json["name"]
    assert len(data.participants) == 3
    first = data.participants[0]
    assert first.id == current_json["starters"][0]["id"]
    assert first.current is not None
    assert first.current.speed == current_json["starters"][0]["current"]["speed"]
    assert isinstance(first.current.time, datetime)
    assert first.current.time.tzinfo is not None


def test_parse_device_may_be_none(current_json: dict[str, Any]) -> None:
    data = RaceData.parse(current_json)
    by_id = data.participants_by_id
    # the starter with device: null
    none_device = next(p for p in data.participants if p.device is None)
    assert none_device.id in by_id


def test_display_name_fallbacks() -> None:
    p = Participant(
        id="x", name=None, start_number="007", marker_color=None,
        tags={}, current=None, device=None,
    )
    assert p.display_name == "#007"
    p2 = Participant(
        id="y", name="Max", start_number=None, marker_color=None,
        tags={}, current=None, device=None,
    )
    assert p2.display_name == "Max"


def test_parse_skips_malformed_starter(current_json: dict[str, Any]) -> None:
    payload = dict(current_json)
    payload["starters"] = [*current_json["starters"], {"no_id": True}]
    data = RaceData.parse(payload)
    assert len(data.participants) == 3  # malformed dropped


def test_racedata_equality(current_json: dict[str, Any]) -> None:
    assert RaceData.parse(current_json) == RaceData.parse(current_json)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: custom_components.racemap.models`.

- [ ] **Step 3: Write exceptions**

`custom_components/racemap/exceptions.py`:
```python
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
```

- [ ] **Step 4: Write models**

`custom_components/racemap/models.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add custom_components/racemap/models.py custom_components/racemap/exceptions.py tests/test_models.py
git commit -m "feat(racemap): add typed data models and exceptions"
```

---

### Task 3: API client

**Files:**
- Create: `custom_components/racemap/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `models.RaceData`, all `exceptions.*`, `const.BASE_URL/REQUEST_TIMEOUT`.
- Produces:
  - `api.RaceMapApiClient(session: aiohttp.ClientSession, token: str, event_id: str)`
  - `async RaceMapApiClient.async_get_current() -> RaceData`

- [ ] **Step 1: Write the failing test**

`tests/test_api.py`:
```python
"""Tests for the RaceMap API client."""

from __future__ import annotations

from typing import Any

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from custom_components.racemap.api import RaceMapApiClient
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)

EVENT_ID = "evt123"
URL = f"https://racemap.com/api/data/v1/{EVENT_ID}/current"


@pytest.fixture
async def client() -> RaceMapApiClient:
    async with ClientSession() as session:
        yield RaceMapApiClient(session, "secret-token", EVENT_ID)


async def test_get_current_success(
    client: RaceMapApiClient, current_json: dict[str, Any]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=200, payload=current_json)
        data = await client.async_get_current()
    assert data.event.name == current_json["name"]
    assert len(data.participants) == 3


async def test_get_current_sends_bearer_token(
    client: RaceMapApiClient, current_json: dict[str, Any]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=200, payload=current_json)
        await client.async_get_current()
        request = next(iter(m.requests.values()))[0]
    assert request.kwargs["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, RaceMapAuthError),
        (403, RaceMapAuthError),
        (404, RaceMapEventNotFoundError),
        (500, RaceMapConnectionError),
        (502, RaceMapConnectionError),
    ],
)
async def test_get_current_status_errors(
    client: RaceMapApiClient, status: int, expected: type[Exception]
) -> None:
    with aioresponses() as m:
        m.get(URL, status=status)
        with pytest.raises(expected):
            await client.async_get_current()


async def test_get_current_rate_limited(client: RaceMapApiClient) -> None:
    with aioresponses() as m:
        m.get(URL, status=429, headers={"Retry-After": "42"})
        with pytest.raises(RaceMapRateLimitError) as err:
            await client.async_get_current()
    assert err.value.retry_after == 42.0


async def test_get_current_network_error(client: RaceMapApiClient) -> None:
    with aioresponses() as m:
        m.get(URL, exception=TimeoutError())
        with pytest.raises(RaceMapConnectionError):
            await client.async_get_current()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: custom_components.racemap.api`.

- [ ] **Step 3: Write the client**

`custom_components/racemap/api.py`:
```python
"""RaceMap API client."""

from __future__ import annotations

import asyncio
import time

import aiohttp

from .const import BASE_URL, LOGGER, REQUEST_TIMEOUT
from .exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)
from .models import RaceData


class RaceMapApiClient:
    """Client for the RaceMap live data API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        event_id: str,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._token = token
        self._event_id = event_id

    @property
    def _url(self) -> str:
        """Return the /current endpoint URL."""
        return f"{BASE_URL}/api/data/v1/{self._event_id}/current"

    async def async_get_current(self) -> RaceData:
        """Fetch and parse the current race data."""
        headers = {"Authorization": f"Bearer {self._token}"}
        started = time.monotonic()
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(self._url, headers=headers)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RaceMapConnectionError(
                f"Error connecting to RaceMap: {err}"
            ) from err

        LOGGER.debug(
            "RaceMap GET /current event=%s status=%s duration=%.3fs",
            self._event_id,
            response.status,
            time.monotonic() - started,
        )

        if response.status in (401, 403):
            raise RaceMapAuthError("Invalid RaceMap API token")
        if response.status == 404:
            raise RaceMapEventNotFoundError(
                f"RaceMap event {self._event_id} not found"
            )
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RaceMapRateLimitError(
                float(retry_after) if retry_after else None
            )
        if response.status >= 400:
            raise RaceMapConnectionError(
                f"Unexpected RaceMap status {response.status}"
            )

        payload = await response.json()
        data = RaceData.parse(payload)
        LOGGER.debug("RaceMap parsed %d participants", len(data.participants))
        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: PASS (all parametrized cases + success + token + rate-limit + network).

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/api.py tests/test_api.py
git commit -m "feat(racemap): add aiohttp API client with error mapping"
```

---

### Task 4: Coordinator

**Files:**
- Create: `custom_components/racemap/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `api.RaceMapApiClient`, `models.RaceData`, all `exceptions.*`, `const.*`.
- Produces:
  - `coordinator.RaceMapConfigEntry` type alias = `ConfigEntry[RaceMapDataUpdateCoordinator]`
  - `coordinator.RaceMapDataUpdateCoordinator(DataUpdateCoordinator[RaceData])` with attribute `.client` and `__init__(self, hass, entry, client)`

- [ ] **Step 1: Write the failing test**

`tests/test_coordinator.py`:
```python
"""Tests for the RaceMap coordinator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.coordinator import RaceMapDataUpdateCoordinator
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapRateLimitError,
)
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={},
        unique_id="evt123",
    )


async def test_update_success(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.return_value = RaceData.parse(current_json)
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data.event.name == current_json["name"]


async def test_update_auth_error(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapAuthError("bad")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_update_rate_limit(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapRateLimitError(30.0)
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_update_connection_error(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_current.side_effect = RaceMapConnectionError("down")
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError: custom_components.racemap.coordinator`.

- [ ] **Step 3: Write the coordinator**

`custom_components/racemap/coordinator.py`:
```python
"""DataUpdateCoordinator for RaceMap."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RaceMapApiClient
from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .exceptions import (
    RaceMapAuthError,
    RaceMapError,
    RaceMapRateLimitError,
)
from .models import RaceData

type RaceMapConfigEntry = ConfigEntry[RaceMapDataUpdateCoordinator]


class RaceMapDataUpdateCoordinator(DataUpdateCoordinator[RaceData]):
    """Coordinate a single /current poll for all entities."""

    config_entry: RaceMapConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RaceMapConfigEntry,
        client: RaceMapApiClient,
    ) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=interval),
            always_update=False,
        )
        self.client = client

    async def _async_update_data(self) -> RaceData:
        """Fetch data from the RaceMap API."""
        try:
            return await self.client.async_get_current()
        except RaceMapAuthError as err:
            raise ConfigEntryAuthFailed(
                "Authentication with RaceMap failed"
            ) from err
        except RaceMapRateLimitError as err:
            raise UpdateFailed(
                "RaceMap API rate limit exceeded",
                retry_after=err.retry_after,
            ) from err
        except RaceMapError as err:
            raise UpdateFailed(f"Error updating RaceMap data: {err}") from err
```

Note: if the installed HA version's `UpdateFailed` does not accept `retry_after`, drop that kwarg (the base coordinator handles backoff regardless); keep the raise.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/coordinator.py tests/test_coordinator.py
git commit -m "feat(racemap): add DataUpdateCoordinator with error handling"
```

---

### Task 5: Manifest, entity base, and __init__ setup

**Files:**
- Create: `custom_components/racemap/manifest.json`
- Create: `custom_components/racemap/entity.py`
- Modify: `custom_components/racemap/__init__.py` (replace the marker)
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `coordinator.RaceMapDataUpdateCoordinator`, `coordinator.RaceMapConfigEntry`, `api.RaceMapApiClient`, `models.*`, `const.*`.
- Produces:
  - `__init__.PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]`
  - `async __init__.async_setup_entry(hass, entry) -> bool`
  - `async __init__.async_unload_entry(hass, entry) -> bool`
  - `entity.event_device_info(entry, event) -> DeviceInfo`
  - `entity.participant_device_info(entry, participant) -> DeviceInfo`
  - `entity.RaceMapEntity(CoordinatorEntity[RaceMapDataUpdateCoordinator])` base with `_attr_has_entity_name = True`, `_attr_attribution`

- [ ] **Step 1: Write the manifest**

`custom_components/racemap/manifest.json`:
```json
{
  "domain": "racemap",
  "name": "RaceMap",
  "codeowners": ["@your-github-handle"],
  "config_flow": true,
  "documentation": "https://github.com/your-github-handle/racemap-ha",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/your-github-handle/racemap-ha/issues",
  "loggers": ["custom_components.racemap"],
  "quality_scale": "silver",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_init.py`:
```python
"""Tests for RaceMap setup/unload."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.exceptions import RaceMapConnectionError
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={},
        unique_id="evt123",
        title="Race",
    )


async def test_setup_and_unload(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_not_ready(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        side_effect=RaceMapConnectionError("down"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_init.py -v`
Expected: FAIL (setup returns nothing / platforms missing / no runtime_data).

- [ ] **Step 4: Write the entity base**

`custom_components/racemap/entity.py`:
```python
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
```

- [ ] **Step 5: Write __init__**

`custom_components/racemap/__init__.py`:
```python
"""The RaceMap integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RaceMapApiClient
from .const import CONF_EVENT_ID, CONF_TOKEN
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]


async def async_setup_entry(
    hass: HomeAssistant, entry: RaceMapConfigEntry
) -> bool:
    """Set up RaceMap from a config entry."""
    session = async_get_clientsession(hass)
    client = RaceMapApiClient(
        session, entry.data[CONF_TOKEN], entry.data[CONF_EVENT_ID]
    )
    coordinator = RaceMapDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RaceMapConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

Note: setup will fail platform forwarding until Tasks 7-8 create `sensor.py`/`device_tracker.py`. To keep this task independently green, temporarily set `PLATFORMS = []` OR create empty platform stubs (`async def async_setup_entry(...): return True`? — no: platforms need `async_setup_entry`). Simplest: set `PLATFORMS: list[Platform] = []` in this task, and change it to `[Platform.SENSOR, Platform.DEVICE_TRACKER]` in Task 8 Step for wiring. The `test_init.py` tests do not assert entities, so `PLATFORMS = []` passes here.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_init.py -v`
Expected: PASS (2 tests). `test_setup_not_ready` → `SETUP_RETRY` because `ConfigEntryNotReady` is raised by `async_config_entry_first_refresh` on `UpdateFailed`.

- [ ] **Step 7: Commit**

```bash
git add custom_components/racemap/manifest.json custom_components/racemap/entity.py custom_components/racemap/__init__.py tests/test_init.py
git commit -m "feat(racemap): add manifest, entity base, setup/unload"
```

---

### Task 6: Config flow (user, reauth, reconfigure) + options flow

**Files:**
- Create: `custom_components/racemap/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `api.RaceMapApiClient`, all `exceptions.*`, `const.*`, `coordinator.RaceMapConfigEntry`, `models.RaceData`.
- Produces:
  - `config_flow.RaceMapConfigFlow(ConfigFlow, domain=DOMAIN)` with steps `user`, `reauth`, `reauth_confirm`, `reconfigure`, and `async_get_options_flow`
  - `config_flow.RaceMapOptionsFlow(OptionsFlowWithReload)` with step `init`

- [ ] **Step 1: Write the failing test**

`tests/test_config_flow.py`:
```python
"""Tests for the RaceMap config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.racemap.exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapEventNotFoundError,
)
from custom_components.racemap.models import RaceData

USER_INPUT = {CONF_TOKEN: "secret", CONF_EVENT_ID: "evt123"}


def _patch_get_current(current_json: dict[str, Any], **kw: Any):
    return patch(
        "custom_components.racemap.config_flow.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
        **kw,
    )


async def test_user_flow_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == "evt123"


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (RaceMapAuthError("x"), "invalid_auth"),
        (RaceMapEventNotFoundError("x"), "event_not_found"),
        (RaceMapConnectionError("x"), "cannot_connect"),
        (ValueError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, exc: Exception, error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with patch(
        "custom_components.racemap.config_flow.RaceMapApiClient.async_get_current",
        side_effect=exc,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_flow_duplicate(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT).add_to_hass(
        hass
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT)
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "newtoken"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "newtoken"


async def test_reconfigure_success(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="evt123", data=USER_INPUT)
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    with _patch_get_current(current_json):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "t2", CONF_EVENT_ID: "evt123"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_TOKEN] == "t2"


async def test_options_flow(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="evt123", data=USER_INPUT, options={}
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        participant_id = current_json["starters"][0]["id"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_UPDATE_INTERVAL: 60, CONF_PARTICIPANTS: [participant_id]},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 60
    assert entry.options[CONF_PARTICIPANTS] == [participant_id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: custom_components.racemap.config_flow`.

- [ ] **Step 3: Write the config flow**

`custom_components/racemap/config_flow.py`:
```python
"""Config and options flow for RaceMap."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import RaceMapApiClient
from .const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_UPDATE_INTERVAL,
)
from .coordinator import RaceMapConfigEntry, RaceMapDataUpdateCoordinator
from .exceptions import (
    RaceMapAuthError,
    RaceMapConnectionError,
    RaceMapError,
    RaceMapEventNotFoundError,
    RaceMapRateLimitError,
)
from .models import RaceData

TOKEN_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)


async def _validate(
    hass: Any, token: str, event_id: str
) -> tuple[RaceData | None, str | None]:
    """Validate credentials; return (data, error_key)."""
    session = async_get_clientsession(hass)
    client = RaceMapApiClient(session, token, event_id)
    try:
        return await client.async_get_current(), None
    except RaceMapAuthError:
        return None, "invalid_auth"
    except RaceMapEventNotFoundError:
        return None, "event_not_found"
    except (RaceMapConnectionError, RaceMapRateLimitError):
        return None, "cannot_connect"
    except RaceMapError:
        return None, "cannot_connect"
    except Exception:  # noqa: BLE001
        LOGGER.exception("Unexpected error validating RaceMap connection")
        return None, "unknown"


class RaceMapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RaceMap."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], user_input[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(user_input[CONF_EVENT_ID])
                self._abort_if_unique_id_configured()
                title = (data.event.name if data else None) or user_input[
                    CONF_EVENT_ID
                ]
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                    vol.Required(CONF_EVENT_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth on auth failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth with a new token."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], entry.data[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(entry.data[CONF_EVENT_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of token/event id."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            data, error = await _validate(
                self.hass, user_input[CONF_TOKEN], user_input[CONF_EVENT_ID]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(user_input[CONF_EVENT_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TOKEN, default=entry.data[CONF_TOKEN]
                    ): TOKEN_SELECTOR,
                    vol.Required(
                        CONF_EVENT_ID, default=entry.data[CONF_EVENT_ID]
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: RaceMapConfigEntry,
    ) -> RaceMapOptionsFlow:
        """Return the options flow."""
        return RaceMapOptionsFlow()


class RaceMapOptionsFlow(OptionsFlowWithReload):
    """Handle RaceMap options (refresh interval + participants)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        coordinator: RaceMapDataUpdateCoordinator | None = getattr(
            self.config_entry, "runtime_data", None
        )
        options: list[SelectOptionDict] = []
        if coordinator is not None and coordinator.data is not None:
            options = [
                SelectOptionDict(
                    value=p.id,
                    label=f"{p.display_name} (#{p.start_number})"
                    if p.start_number
                    else p.display_name,
                )
                for p in coordinator.data.participants
            ]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL,
                        max=3600,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Optional(CONF_PARTICIPANTS, default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        custom_value=True,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, self.config_entry.options
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: PASS (user success, 3 error cases, duplicate abort, reauth, reconfigure, options).

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/config_flow.py tests/test_config_flow.py
git commit -m "feat(racemap): add config, reauth, reconfigure, and options flows"
```

---

### Task 7: Sensor platform

**Files:**
- Create: `custom_components/racemap/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `entity.RaceMapEntity`/`event_device_info`/`participant_device_info`, `coordinator.*`, `models.*`, `const.*`.
- Produces:
  - `sensor.PARALLEL_UPDATES = 0`
  - `async sensor.async_setup_entry(hass, entry, async_add_entities) -> None`
  - `sensor.EVENT_SENSORS`, `sensor.PARTICIPANT_SENSORS`, `sensor.PARTICIPANT_DIAGNOSTIC_SENSORS` description tuples
  - helper `sensor.selected_participants(entry, data) -> list[Participant]` (shared with device_tracker via re-import)

- [ ] **Step 1: Write the failing test**

`tests/test_sensor.py`:
```python
"""Tests for RaceMap sensors."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry(current_json: dict[str, Any]) -> MockConfigEntry:
    pid = current_json["starters"][0]["id"]
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [pid]},
        title="Race",
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: RaceData) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_event_sensors_created(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    await _setup(hass, entry, RaceData.parse(current_json))
    state = hass.states.get("sensor.race_participant_count")
    assert state is not None
    assert state.state == "3"


async def test_participant_speed_sensor(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    data = RaceData.parse(current_json)
    await _setup(hass, entry, data)
    pid = current_json["starters"][0]["id"]
    # find the entity by unique_id via entity registry
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    ent = registry.async_get_entity_id("sensor", DOMAIN, f"evt123_{pid}_speed")
    assert ent is not None
    state = hass.states.get(ent)
    assert state is not None
    assert float(state.state) == current_json["starters"][0]["current"]["speed"]


async def test_diagnostic_sensor_absent_when_no_device(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    # select the participant whose device is null
    none_device = next(
        s for s in current_json["starters"] if s.get("device") is None
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [none_device["id"]]},
        title="Race",
    )
    await _setup(hass, entry, RaceData.parse(current_json))
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    ent = registry.async_get_entity_id(
        "sensor", DOMAIN, f"evt123_{none_device['id']}_battery"
    )
    assert ent is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sensor.py -v`
Expected: FAIL (no `sensor.py` / entities not created).

- [ ] **Step 3: Write the sensor platform**

`custom_components/racemap/sensor.py`:
```python
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
    EntityCategory,
    PERCENTAGE,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_PARTICIPANTS
from .coordinator import RaceMapConfigEntry
from .entity import RaceMapEntity, event_device_info, participant_device_info
from .models import EventInfo, Participant, RaceData

PARALLEL_UPDATES = 0

type EventValueFn = Callable[[EventInfo], StateType | datetime]
type ParticipantValueFn = Callable[[Participant], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class RaceMapEventSensorDescription(SensorEntityDescription):
    """Describes an event sensor."""

    value_fn: EventValueFn


@dataclass(frozen=True, kw_only=True)
class RaceMapParticipantSensorDescription(SensorEntityDescription):
    """Describes a participant sensor."""

    value_fn: ParticipantValueFn
    exists_fn: Callable[[Participant], bool] = lambda _: True


def _c(p: Participant):  # noqa: ANN202
    """Return the current object (may be None)."""
    return p.current


EVENT_SENSORS: tuple[RaceMapEventSensorDescription, ...] = (
    RaceMapEventSensorDescription(
        key="event_location",
        translation_key="event_location",
        value_fn=lambda e: e.location,
    ),
    RaceMapEventSensorDescription(
        key="start_time",
        translation_key="start_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda e: e.start_time,
    ),
    RaceMapEventSensorDescription(
        key="end_time",
        translation_key="end_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda e: e.end_time,
    ),
    RaceMapEventSensorDescription(
        key="result_time",
        translation_key="result_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda e: e.result_time,
    ),
)

PARTICIPANT_COUNT = RaceMapEventSensorDescription(
    key="participant_count",
    translation_key="participant_count",
    state_class=SensorStateClass.MEASUREMENT,
    value_fn=lambda e: None,  # replaced below via RaceData
)


def _cur(p: Participant, attr: str) -> StateType:
    """Read a float attribute off current, or None."""
    if p.current is None:
        return None
    return getattr(p.current, attr)


PARTICIPANT_SENSORS: tuple[RaceMapParticipantSensorDescription, ...] = (
    RaceMapParticipantSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        value_fn=lambda p: _cur(p, "speed"),
    ),
    RaceMapParticipantSensorDescription(
        key="from_start",
        translation_key="from_start",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda p: _cur(p, "from_start"),
    ),
    RaceMapParticipantSensorDescription(
        key="to_finish",
        translation_key="to_finish",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda p: _cur(p, "to_finish"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_distance",
        translation_key="gap_distance",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda p: _cur(p, "gap_distance"),
    ),
    RaceMapParticipantSensorDescription(
        key="eta",
        translation_key="eta",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda p: _cur(p, "eta"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap",
        translation_key="gap",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda p: _cur(p, "gap"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_chase",
        translation_key="gap_chase",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "gap_chase"),
    ),
    RaceMapParticipantSensorDescription(
        key="gap_average",
        translation_key="gap_average",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "gap_average"),
    ),
    RaceMapParticipantSensorDescription(
        key="distance_to_shadow_track",
        translation_key="distance_to_shadow_track",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "distance_to_shadow_track"),
    ),
    RaceMapParticipantSensorDescription(
        key="elevation",
        translation_key="elevation",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfLength.METERS,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "elv"),
    ),
    RaceMapParticipantSensorDescription(
        key="latitude",
        translation_key="latitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "lat"),
    ),
    RaceMapParticipantSensorDescription(
        key="longitude",
        translation_key="longitude",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=DEGREE,
        entity_registry_enabled_default=False,
        value_fn=lambda p: _cur(p, "lng"),
    ),
    RaceMapParticipantSensorDescription(
        key="current_time",
        translation_key="current_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda p: _cur(p, "time"),
    ),
)

PARTICIPANT_DIAGNOSTIC_SENSORS: tuple[
    RaceMapParticipantSensorDescription, ...
] = (
    RaceMapParticipantSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda p: p.device is not None,
        value_fn=lambda p: p.device.battery if p.device else None,
    ),
    RaceMapParticipantSensorDescription(
        key="last_location_at",
        translation_key="last_location_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda p: p.device is not None,
        value_fn=lambda p: p.device.last_location_at if p.device else None,
    ),
    RaceMapParticipantSensorDescription(
        key="online",
        translation_key="online",
        device_class=SensorDeviceClass.ENUM,
        options=["connected", "disconnected"],
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda p: p.device is not None,
        value_fn=lambda p: (
            None
            if p.device is None or p.device.online is None
            else ("connected" if p.device.online else "disconnected")
        ),
    ),
)


def selected_participants(
    entry: RaceMapConfigEntry, data: RaceData
) -> list[Participant]:
    """Return participants selected in options that exist in the data."""
    selected = set(entry.options.get(CONF_PARTICIPANTS, []))
    by_id = data.participants_by_id
    return [by_id[pid] for pid in selected if pid in by_id]


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

    known: set[str] = set()

    @callback
    def _add_participant_entities() -> None:
        new: list[SensorEntity] = []
        for participant in selected_participants(entry, coordinator.data):
            if participant.id in known:
                continue
            known.add(participant.id)
            for description in PARTICIPANT_SENSORS + PARTICIPANT_DIAGNOSTIC_SENSORS:
                if description.exists_fn(participant):
                    new.append(
                        RaceMapParticipantSensor(
                            coordinator, entry, participant.id, description
                        )
                    )
        if new:
            async_add_entities(new)

    _add_participant_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_participant_entities))
    async_add_entities(entities)


class RaceMapEventSensor(RaceMapEntity, SensorEntity):
    """A sensor on the event device."""

    entity_description: RaceMapEventSensorDescription

    def __init__(
        self, coordinator, entry, description: RaceMapEventSensorDescription
    ) -> None:
        """Initialize the event sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = event_device_info(entry, coordinator.data.event)

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data.event)


class RaceMapParticipantCountSensor(RaceMapEntity, SensorEntity):
    """Number of participants in the event."""

    _attr_translation_key = "participant_count"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry) -> None:
        """Initialize the count sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_participant_count"
        self._attr_device_info = event_device_info(entry, coordinator.data.event)

    @property
    def native_value(self) -> int:
        """Return the participant count."""
        return len(self.coordinator.data.participants)


class RaceMapParticipantSensor(RaceMapEntity, SensorEntity):
    """A sensor on a participant device."""

    entity_description: RaceMapParticipantSensorDescription

    def __init__(
        self,
        coordinator,
        entry,
        participant_id: str,
        description: RaceMapParticipantSensorDescription,
    ) -> None:
        """Initialize the participant sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._participant_id = participant_id
        self.entity_description = description
        event_id = entry.data["event_id"]
        self._attr_unique_id = f"{event_id}_{participant_id}_{description.key}"
        participant = coordinator.data.participants_by_id[participant_id]
        self._attr_device_info = participant_device_info(entry, participant)

    @property
    def _participant(self) -> Participant | None:
        """Return the current participant or None."""
        return self.coordinator.data.participants_by_id.get(self._participant_id)

    @property
    def available(self) -> bool:
        """Return availability."""
        participant = self._participant
        if not super().available or participant is None:
            return False
        return self.entity_description.value_fn(participant) is not None

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        participant = self._participant
        if participant is None:
            return None
        return self.entity_description.value_fn(participant)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sensor.py -v`
Expected: PASS (event sensors incl. count == "3", participant speed matches fixture, battery absent when device is null).

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/sensor.py tests/test_sensor.py
git commit -m "feat(racemap): add sensor platform for event and participants"
```

---

### Task 8: Device tracker platform + wire up PLATFORMS

**Files:**
- Create: `custom_components/racemap/device_tracker.py`
- Modify: `custom_components/racemap/__init__.py` (set `PLATFORMS = [Platform.SENSOR, Platform.DEVICE_TRACKER]`)
- Test: `tests/test_device_tracker.py`

**Interfaces:**
- Consumes: `entity.RaceMapEntity`/`participant_device_info`, `sensor.selected_participants`, `coordinator.*`, `models.Participant`.
- Produces:
  - `device_tracker.PARALLEL_UPDATES = 0`
  - `async device_tracker.async_setup_entry(hass, entry, async_add_entities) -> None`
  - `device_tracker.RaceMapDeviceTracker(RaceMapEntity, TrackerEntity)`

- [ ] **Step 1: Write the failing test**

`tests/test_device_tracker.py`:
```python
"""Tests for the RaceMap device tracker."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


@pytest.fixture
def entry(current_json: dict[str, Any]) -> MockConfigEntry:
    pid = current_json["starters"][0]["id"]
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [pid]},
        title="Race",
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry, data: RaceData) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_tracker_reports_coordinates(
    hass: HomeAssistant, entry: MockConfigEntry, current_json: dict[str, Any]
) -> None:
    data = RaceData.parse(current_json)
    await _setup(hass, entry, data)
    pid = current_json["starters"][0]["id"]
    registry = er.async_get(hass)
    ent = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{pid}_tracker"
    )
    assert ent is not None
    state = hass.states.get(ent)
    assert state is not None
    cur = current_json["starters"][0]["current"]
    assert state.attributes["latitude"] == cur["lat"]
    assert state.attributes["longitude"] == cur["lng"]


async def test_tracker_unavailable_without_location(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    payload = copy.deepcopy(current_json)
    payload["starters"][0]["current"] = None
    pid = payload["starters"][0]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [pid]},
        title="Race",
    )
    await _setup(hass, entry, RaceData.parse(payload))
    registry = er.async_get(hass)
    ent = registry.async_get_entity_id(
        "device_tracker", DOMAIN, f"evt123_{pid}_tracker"
    )
    assert ent is not None
    state = hass.states.get(ent)
    assert state is not None
    assert state.state == "unavailable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_device_tracker.py -v`
Expected: FAIL (no `device_tracker.py`; also entity not created because `__init__.PLATFORMS` may still be `[]` from Task 5).

- [ ] **Step 3: Wire up PLATFORMS in __init__**

In `custom_components/racemap/__init__.py`, ensure:
```python
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.DEVICE_TRACKER]
```
(Change from the Task 5 temporary `[]`.)

- [ ] **Step 4: Write the device tracker**

`custom_components/racemap/device_tracker.py`:
```python
"""Device tracker platform for RaceMap."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

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
    known: set[str] = set()

    @callback
    def _add() -> None:
        new: list[RaceMapDeviceTracker] = []
        for participant in selected_participants(entry, coordinator.data):
            if participant.id in known:
                continue
            known.add(participant.id)
            new.append(RaceMapDeviceTracker(coordinator, entry, participant.id))
        if new:
            async_add_entities(new)

    _add()
    entry.async_on_unload(coordinator.async_add_listener(_add))


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
        event_id = entry.data["event_id"]
        self._attr_unique_id = f"{event_id}_{participant_id}_tracker"
        participant = coordinator.data.participants_by_id[participant_id]
        self._attr_device_info = participant_device_info(entry, participant)

    @property
    def _participant(self) -> Participant | None:
        """Return the current participant or None."""
        return self.coordinator.data.participants_by_id.get(self._participant_id)

    @property
    def available(self) -> bool:
        """Return availability based on presence of coordinates."""
        participant = self._participant
        if not super().available or participant is None:
            return False
        current = participant.current
        return current is not None and current.lat is not None and current.lng is not None

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        participant = self._participant
        if participant is None or participant.current is None:
            return None
        return participant.current.lat

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        participant = self._participant
        if participant is None or participant.current is None:
            return None
        return participant.current.lng
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_device_tracker.py tests/test_init.py -v`
Expected: PASS (coordinates reported; unavailable when `current` is null; init tests still green with real platforms).

- [ ] **Step 6: Commit**

```bash
git add custom_components/racemap/device_tracker.py custom_components/racemap/__init__.py tests/test_device_tracker.py
git commit -m "feat(racemap): add participant GPS device tracker"
```

---

### Task 9: Diagnostics

**Files:**
- Create: `custom_components/racemap/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `coordinator.RaceMapConfigEntry`, `const.CONF_TOKEN`, `dataclasses.asdict`.
- Produces: `async diagnostics.async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

`tests/test_diagnostics.py`:
```python
"""Tests for RaceMap diagnostics."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import CONF_EVENT_ID, CONF_TOKEN, DOMAIN
from custom_components.racemap.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.racemap.models import RaceData


async def test_diagnostics_redacts_token(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "super-secret", CONF_EVENT_ID: "evt123"},
        options={},
        title="Race",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=RaceData.parse(current_json),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["entry"]["data"][CONF_TOKEN] != "super-secret"
    assert result["data"]["event"]["name"] == current_json["name"]
    assert len(result["data"]["participants"]) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError: custom_components.racemap.diagnostics`.

- [ ] **Step 3: Write diagnostics**

`custom_components/racemap/diagnostics.py`:
```python
"""Diagnostics support for RaceMap."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import RaceMapConfigEntry

TO_REDACT = {CONF_TOKEN, "token", "Authorization"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RaceMapConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "data": {
            "event": asdict(data.event),
            "participants": [asdict(p) for p in data.participants],
        },
    }
```

Note: `asdict` serializes `datetime` objects as-is; HA's diagnostics JSON encoder handles datetimes. If a serialization error surfaces in the test, wrap datetimes via `str()` in a small recursive helper — but the default HA encoder supports datetime, so this should pass unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_diagnostics.py -v`
Expected: PASS (token redacted, event + 3 participants present).

- [ ] **Step 5: Commit**

```bash
git add custom_components/racemap/diagnostics.py tests/test_diagnostics.py
git commit -m "feat(racemap): add diagnostics with token redaction"
```

---

### Task 10: Translations, icons, and quality_scale.yaml

**Files:**
- Create: `custom_components/racemap/strings.json`
- Create: `custom_components/racemap/translations/en.json`
- Create: `custom_components/racemap/translations/de.json`
- Create: `custom_components/racemap/icons.json`
- Create: `custom_components/racemap/quality_scale.yaml`
- Test: `tests/test_translations.py`

**Interfaces:**
- Consumes: the `translation_key` values used in Task 7 (`event_location`, `start_time`, `end_time`, `result_time`, `participant_count`, `speed`, `from_start`, `to_finish`, `gap_distance`, `eta`, `gap`, `gap_chase`, `gap_average`, `distance_to_shadow_track`, `elevation`, `latitude`, `longitude`, `current_time`, `battery`, `last_location_at`, `online`) and the flow step/error/abort keys from Task 6.
- Produces: complete i18n + icon + quality tracking files.

- [ ] **Step 1: Write the failing test**

`tests/test_translations.py`:
```python
"""Structural validation of translation and icon files."""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path("custom_components/racemap")

SENSOR_KEYS = {
    "event_location", "start_time", "end_time", "result_time",
    "participant_count", "speed", "from_start", "to_finish", "gap_distance",
    "eta", "gap", "gap_chase", "gap_average", "distance_to_shadow_track",
    "elevation", "latitude", "longitude", "current_time", "battery",
    "last_location_at", "online",
}


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def test_strings_and_en_match() -> None:
    strings = _load("strings.json")
    en = _load("translations/en.json")
    assert strings == en


def test_config_steps_present() -> None:
    strings = _load("strings.json")
    steps = strings["config"]["step"]
    assert {"user", "reauth_confirm", "reconfigure"} <= set(steps)
    errors = strings["config"]["error"]
    assert {"cannot_connect", "invalid_auth", "event_not_found", "unknown"} <= set(
        errors
    )
    aborts = strings["config"]["abort"]
    assert {"already_configured", "reauth_successful", "reconfigure_successful"} <= set(
        aborts
    )


def test_all_sensor_keys_translated() -> None:
    strings = _load("strings.json")
    names = set(strings["entity"]["sensor"])
    assert SENSOR_KEYS <= names


def test_de_has_same_toplevel_keys() -> None:
    en = _load("translations/en.json")
    de = _load("translations/de.json")
    assert set(en) == set(de)


def test_icons_cover_selected_keys() -> None:
    icons = _load("icons.json")["entity"]["sensor"]
    assert {"speed", "from_start", "to_finish", "eta", "gap", "online"} <= set(icons)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_translations.py -v`
Expected: FAIL (files missing).

- [ ] **Step 3: Write strings.json**

`custom_components/racemap/strings.json`:
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to RaceMap",
        "data": { "token": "API token", "event_id": "Event ID" },
        "data_description": {
          "token": "Your RaceMap API token (Account settings \u2192 API Tokens).",
          "event_id": "The ID of the event you want to track."
        }
      },
      "reauth_confirm": {
        "title": "Re-authenticate RaceMap",
        "description": "The RaceMap API token is no longer valid. Enter a new token.",
        "data": { "token": "API token" },
        "data_description": { "token": "A new, valid RaceMap API token." }
      },
      "reconfigure": {
        "title": "Reconfigure RaceMap",
        "data": { "token": "API token", "event_id": "Event ID" },
        "data_description": {
          "token": "Your RaceMap API token.",
          "event_id": "The ID of the event you want to track."
        }
      }
    },
    "error": {
      "cannot_connect": "Failed to connect to RaceMap. Please try again.",
      "invalid_auth": "Invalid API token.",
      "event_not_found": "No event was found for this event ID.",
      "unknown": "An unexpected error occurred."
    },
    "abort": {
      "already_configured": "This event is already configured.",
      "reauth_successful": "Re-authentication was successful.",
      "reconfigure_successful": "Reconfiguration was successful.",
      "unique_id_mismatch": "The event ID does not match the existing configuration."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "RaceMap options",
        "data": {
          "update_interval": "Update interval (seconds)",
          "participants": "Tracked participants"
        },
        "data_description": {
          "update_interval": "How often to poll RaceMap for new data.",
          "participants": "Participants to create devices and entities for."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "event_location": { "name": "Location" },
      "start_time": { "name": "Start time" },
      "end_time": { "name": "End time" },
      "result_time": { "name": "Last update" },
      "participant_count": { "name": "Participants" },
      "speed": { "name": "Speed" },
      "from_start": { "name": "Distance from start" },
      "to_finish": { "name": "Distance to finish" },
      "gap_distance": { "name": "Gap distance" },
      "eta": { "name": "Estimated time of arrival" },
      "gap": { "name": "Gap" },
      "gap_chase": { "name": "Gap (chase)" },
      "gap_average": { "name": "Gap (average)" },
      "distance_to_shadow_track": { "name": "Distance to track" },
      "elevation": { "name": "Elevation" },
      "latitude": { "name": "Latitude" },
      "longitude": { "name": "Longitude" },
      "current_time": { "name": "Last position time" },
      "battery": { "name": "Battery" },
      "last_location_at": { "name": "Last location" },
      "online": {
        "name": "Connection",
        "state": { "connected": "Connected", "disconnected": "Disconnected" }
      }
    }
  },
  "exceptions": {
    "cannot_connect": { "message": "Failed to connect to RaceMap." },
    "invalid_auth": { "message": "Authentication with RaceMap failed." },
    "event_not_found": { "message": "The RaceMap event was not found." },
    "rate_limited": { "message": "The RaceMap API rate limit was exceeded." }
  }
}
```

- [ ] **Step 4: Create en.json as a copy of strings.json**

`custom_components/racemap/translations/en.json`: identical content to `strings.json` (the `test_strings_and_en_match` test enforces this). Copy the exact bytes.

- [ ] **Step 5: Write de.json**

`custom_components/racemap/translations/de.json`: same structure as en.json, German values. Must have identical top-level keys. Example values:
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Mit RaceMap verbinden",
        "data": { "token": "API-Token", "event_id": "Event-ID" },
        "data_description": {
          "token": "Dein RaceMap API-Token (Kontoeinstellungen \u2192 API Tokens).",
          "event_id": "Die ID des zu verfolgenden Events."
        }
      },
      "reauth_confirm": {
        "title": "RaceMap erneut authentifizieren",
        "description": "Das RaceMap API-Token ist ung\u00fcltig. Bitte gib ein neues Token ein.",
        "data": { "token": "API-Token" },
        "data_description": { "token": "Ein neues, g\u00fcltiges RaceMap API-Token." }
      },
      "reconfigure": {
        "title": "RaceMap neu konfigurieren",
        "data": { "token": "API-Token", "event_id": "Event-ID" },
        "data_description": {
          "token": "Dein RaceMap API-Token.",
          "event_id": "Die ID des zu verfolgenden Events."
        }
      }
    },
    "error": {
      "cannot_connect": "Verbindung zu RaceMap fehlgeschlagen. Bitte erneut versuchen.",
      "invalid_auth": "Ung\u00fcltiges API-Token.",
      "event_not_found": "Kein Event f\u00fcr diese Event-ID gefunden.",
      "unknown": "Ein unerwarteter Fehler ist aufgetreten."
    },
    "abort": {
      "already_configured": "Dieses Event ist bereits konfiguriert.",
      "reauth_successful": "Die erneute Authentifizierung war erfolgreich.",
      "reconfigure_successful": "Die Neukonfiguration war erfolgreich.",
      "unique_id_mismatch": "Die Event-ID stimmt nicht mit der bestehenden Konfiguration \u00fcberein."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "RaceMap-Optionen",
        "data": {
          "update_interval": "Aktualisierungsintervall (Sekunden)",
          "participants": "Beobachtete Teilnehmer"
        },
        "data_description": {
          "update_interval": "Wie oft RaceMap nach neuen Daten abgefragt wird.",
          "participants": "Teilnehmer, f\u00fcr die Ger\u00e4te und Entit\u00e4ten erstellt werden."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "event_location": { "name": "Ort" },
      "start_time": { "name": "Startzeit" },
      "end_time": { "name": "Endzeit" },
      "result_time": { "name": "Letzte Aktualisierung" },
      "participant_count": { "name": "Teilnehmer" },
      "speed": { "name": "Geschwindigkeit" },
      "from_start": { "name": "Distanz ab Start" },
      "to_finish": { "name": "Distanz bis Ziel" },
      "gap_distance": { "name": "R\u00fcckstand (Distanz)" },
      "eta": { "name": "Voraussichtliche Ankunft" },
      "gap": { "name": "R\u00fcckstand" },
      "gap_chase": { "name": "R\u00fcckstand (Verfolger)" },
      "gap_average": { "name": "R\u00fcckstand (Durchschnitt)" },
      "distance_to_shadow_track": { "name": "Distanz zur Strecke" },
      "elevation": { "name": "H\u00f6he" },
      "latitude": { "name": "Breitengrad" },
      "longitude": { "name": "L\u00e4ngengrad" },
      "current_time": { "name": "Zeit der letzten Position" },
      "battery": { "name": "Batterie" },
      "last_location_at": { "name": "Letzte Position" },
      "online": {
        "name": "Verbindung",
        "state": { "connected": "Verbunden", "disconnected": "Getrennt" }
      }
    }
  },
  "exceptions": {
    "cannot_connect": { "message": "Verbindung zu RaceMap fehlgeschlagen." },
    "invalid_auth": { "message": "Authentifizierung bei RaceMap fehlgeschlagen." },
    "event_not_found": { "message": "Das RaceMap-Event wurde nicht gefunden." },
    "rate_limited": { "message": "Das RaceMap API-Limit wurde \u00fcberschritten." }
  }
}
```

- [ ] **Step 6: Write icons.json**

`custom_components/racemap/icons.json`:
```json
{
  "entity": {
    "sensor": {
      "event_location": { "default": "mdi:map-marker" },
      "start_time": { "default": "mdi:clock-start" },
      "end_time": { "default": "mdi:clock-end" },
      "result_time": { "default": "mdi:update" },
      "participant_count": { "default": "mdi:account-group" },
      "speed": { "default": "mdi:speedometer" },
      "from_start": { "default": "mdi:map-marker-distance" },
      "to_finish": { "default": "mdi:flag-checkered" },
      "gap_distance": { "default": "mdi:map-marker-distance" },
      "eta": { "default": "mdi:timer-sand" },
      "gap": { "default": "mdi:timer-outline" },
      "gap_chase": { "default": "mdi:timer-outline" },
      "gap_average": { "default": "mdi:timer-outline" },
      "distance_to_shadow_track": { "default": "mdi:map-marker-distance" },
      "elevation": { "default": "mdi:elevation-rise" },
      "current_time": { "default": "mdi:clock-outline" },
      "last_location_at": { "default": "mdi:map-clock" },
      "online": {
        "default": "mdi:lan-connect",
        "state": {
          "connected": "mdi:lan-connect",
          "disconnected": "mdi:lan-disconnect"
        }
      }
    }
  }
}
```

- [ ] **Step 7: Write quality_scale.yaml**

`custom_components/racemap/quality_scale.yaml`:
```yaml
rules:
  # Bronze
  action-setup:
    status: exempt
    comment: Integration provides no service actions.
  appropriate-polling: done
  brands:
    status: exempt
    comment: Custom integration; brands live in the HA brands repo when submitted.
  common-modules: done
  config-flow-test-coverage: done
  config-flow: done
  dependency-transparency: done
  docs-actions:
    status: exempt
    comment: No service actions.
  docs-triggers:
    status: exempt
    comment: No triggers provided.
  docs-conditions:
    status: exempt
    comment: No conditions provided.
  docs-high-level-description: done
  docs-installation-instructions: done
  docs-removal-instructions: done
  entity-event-setup: done
  entity-unique-id: done
  has-entity-name: done
  runtime-data: done
  test-before-configure: done
  test-before-setup: done
  unique-config-entry: done
  # Silver
  action-exceptions:
    status: exempt
    comment: No service actions.
  config-entry-unloading: done
  docs-configuration-parameters: done
  docs-installation-parameters: done
  entity-unavailable: done
  integration-owner: done
  log-when-unavailable: done
  parallel-updates: done
  reauthentication-flow: done
  test-coverage: done
  # Gold
  devices: done
  diagnostics: done
  discovery:
    status: exempt
    comment: RaceMap is a cloud service with no network discovery.
  discovery-update-info:
    status: exempt
    comment: No network discovery; connection is via cloud event ID.
  docs-data-update: done
  docs-examples: done
  docs-known-limitations: done
  docs-supported-devices: done
  docs-supported-functions: done
  docs-troubleshooting: done
  docs-use-cases: done
  dynamic-devices: done
  entity-category: done
  entity-device-class: done
  entity-disabled-by-default: done
  entity-translations: done
  exception-translations: done
  icon-translations: done
  reconfiguration-flow: done
  repair-issues:
    status: exempt
    comment: The only user-actionable failure is auth, handled by the reauth flow.
  stale-devices: done
  # Platinum
  async-dependency: done
  inject-websession: done
  strict-typing: done
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_translations.py -v`
Expected: PASS (strings==en, config steps/errors/aborts present, all sensor keys translated, de matches en top-level, icons cover keys).

- [ ] **Step 9: Commit**

```bash
git add custom_components/racemap/strings.json custom_components/racemap/translations custom_components/racemap/icons.json custom_components/racemap/quality_scale.yaml tests/test_translations.py
git commit -m "feat(racemap): add translations, icon translations, and quality_scale"
```

---

### Task 11: Dynamic/stale device cleanup + full verification

**Files:**
- Modify: `custom_components/racemap/sensor.py` (add stale-device removal on option change)
- Modify: `custom_components/racemap/device_tracker.py` (same)
- Test: `tests/test_dynamic_devices.py`
- Create: `requirements_test.txt`, `pyproject.toml` (ruff/mypy config), `hacs.json`, `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: stale-device removal helper wired into both platforms; project meta files.

- [ ] **Step 1: Write the failing test**

`tests/test_dynamic_devices.py`:
```python
"""Tests for dynamic add and stale removal of participant devices."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.racemap.const import (
    CONF_EVENT_ID,
    CONF_PARTICIPANTS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.racemap.models import RaceData


async def test_add_and_remove_participant_devices(
    hass: HomeAssistant, current_json: dict[str, Any]
) -> None:
    p0 = current_json["starters"][0]["id"]
    p1 = current_json["starters"][1]["id"]
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="evt123",
        data={CONF_TOKEN: "t", CONF_EVENT_ID: "evt123"},
        options={CONF_PARTICIPANTS: [p0, p1]},
        title="Race",
    )
    entry.add_to_hass(hass)
    data = RaceData.parse(current_json)
    with patch(
        "custom_components.racemap.RaceMapApiClient.async_get_current",
        return_value=data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        registry = dr.async_get(hass)
        assert registry.async_get_device({(DOMAIN, f"evt123_{p1}")}) is not None

        # Deselect p1
        hass.config_entries.async_update_entry(
            entry, options={CONF_PARTICIPANTS: [p0]}
        )
        await hass.async_block_till_done()

    registry = dr.async_get(hass)
    assert registry.async_get_device({(DOMAIN, f"evt123_{p0}")}) is not None
    assert registry.async_get_device({(DOMAIN, f"evt123_{p1}")}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dynamic_devices.py -v`
Expected: FAIL — the deselected participant device is still present (no stale cleanup yet).

- [ ] **Step 3: Add stale-device cleanup to both platforms**

In `custom_components/racemap/sensor.py`, add this helper near the top and call it from `async_setup_entry` inside the `_add_participant_entities` listener (before adding new entities):

```python
from homeassistant.helpers import device_registry as dr


@callback
def _cleanup_stale_devices(
    hass: HomeAssistant, entry: RaceMapConfigEntry
) -> None:
    """Remove devices for participants no longer selected/present."""
    event_id = entry.data["event_id"]
    selected = {
        f"{event_id}_{pid}"
        for pid in entry.options.get(CONF_PARTICIPANTS, [])
    }
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain != DOMAIN or identifier == entry.entry_id:
                continue  # event device or foreign
            if identifier not in selected:
                registry.async_update_device(
                    device.id, remove_config_entry_id=entry.entry_id
                )
```

Update the listener body in `async_setup_entry` to call `_cleanup_stale_devices(hass, entry)` first, then add new entities. Import `HomeAssistant` is already present. Because `device_tracker` entities share the same device identifiers and the same config entry, removing the config entry id from the device removes it once no entities remain; the sensor platform performing cleanup is sufficient (do not duplicate in device_tracker to avoid double work — but ensure device_tracker's listener still runs `_add`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dynamic_devices.py -v`
Expected: PASS (p0 device present, p1 device removed after deselection).

- [ ] **Step 5: Add project meta files**

`requirements_test.txt`:
```
homeassistant
pytest
pytest-homeassistant-custom-component
pytest-cov
ruff
mypy
aioresponses
```

`pyproject.toml`:
```toml
[tool.ruff]
target-version = "py313"
line-length = 88

[tool.ruff.lint]
select = ["ALL"]
ignore = ["D203", "D213", "COM812", "ISC001"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "ANN", "D", "SLF001", "PLR2004"]

[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_ignores = true
disallow_any_generics = true

[[tool.mypy.overrides]]
module = "tests.*"
ignore_errors = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`hacs.json`:
```json
{
  "name": "RaceMap",
  "render_readme": true,
  "homeassistant": "2024.12.0"
}
```

`README.md`: high-level description, installation (HACS + manual), prerequisites (RaceMap API token, event ID), configuration parameters (token, event id), options (update interval, participants), supported functionality (event device + participant devices with the sensor list and device_tracker), data-update description (polls `/current` every N seconds via a coordinator), known limitations (shadowtrack-dependent `*` fields are null without a mapped track; no push/webhook; one event per entry), troubleshooting (reauth on invalid token, check event id, enable debug logging for `custom_components.racemap`), removal instructions, and one example automation (notify when a tracked participant's `gap` drops below a threshold). This satisfies the Gold `docs-*` rules referenced in `quality_scale.yaml`.

- [ ] **Step 6: Run the full verification suite**

Run each and confirm output:
```bash
ruff check custom_components/racemap tests
ruff format --check custom_components/racemap tests
mypy custom_components/racemap
pytest --cov=custom_components/racemap --cov-report=term-missing
```
Expected:
- `ruff check`: `All checks passed!`
- `ruff format --check`: no files would be reformatted.
- `mypy`: `Success: no issues found`.
- `pytest`: all tests PASS; coverage ≥95% for every module in `custom_components/racemap` (inspect the term-missing report; add targeted tests for any uncovered lines, e.g. the `unknown` config-flow branch, malformed-participant warning, `_validate` generic `RaceMapError` path).

- [ ] **Step 7: Commit**

```bash
git add custom_components/racemap/sensor.py custom_components/racemap/device_tracker.py tests/test_dynamic_devices.py requirements_test.txt pyproject.toml hacs.json README.md
git commit -m "feat(racemap): add stale-device cleanup, tooling config, and docs"
```

---

## Coverage gap backfill (if needed after Task 11 Step 6)

If `--cov-report=term-missing` shows any module <95%, add focused tests:
- `config_flow.py` `unknown` branch is already covered by the `ValueError` parametrize case in Task 6 (the `except Exception` guard lives in `_validate`, shared by all flow steps). If term-missing still flags a step, add a `reauth`/`reconfigure` variant of the `unknown` test.
- `models.py` `_dt`/`_f` None/invalid paths: unit-test `RaceData.parse` with `startTime: null` and `speed: "abc"`.
- `api.py` 400 branch: parametrize a `400` status → `RaceMapConnectionError`.
- `sensor.py` availability `None` path: select a participant with `current: null`; assert speed sensor state is `unavailable`.

Each backfill test follows the same write→run-fail→(fix if code change)→run-pass→commit cycle.
