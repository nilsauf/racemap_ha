"""Tests for RaceMap data models."""

from __future__ import annotations

import copy
from datetime import datetime
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


def test_parse_skips_malformed_nested_participants(
    current_json: dict[str, Any],
) -> None:
    """Skip malformed nested participant data without losing valid entries."""
    payload = copy.deepcopy(current_json)
    payload["starters"].extend(
        [
            {"id": "bad-battery", "device": {"battery": "not-an-int"}},
            {"id": "bad-current", "current": []},
            {"id": "bad-device", "device": []},
        ]
    )

    data = RaceData.parse(payload)

    assert [participant.id for participant in data.participants] == [
        starter["id"] for starter in current_json["starters"]
    ]


def test_racedata_equality(current_json: dict[str, Any]) -> None:
    assert RaceData.parse(current_json) == RaceData.parse(current_json)
