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
