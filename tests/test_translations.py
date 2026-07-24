"""Structural validation of translation and icon files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE = Path("custom_components/racemap")

SENSOR_KEYS = {
    "event_location",
    "start_time",
    "end_time",
    "result_time",
    "participant_count",
    "speed",
    "from_start",
    "to_finish",
    "gap_distance",
    "eta",
    "gap",
    "gap_chase",
    "gap_average",
    "distance_to_shadow_track",
    "elevation",
    "latitude",
    "longitude",
    "current_time",
    "battery",
    "last_location_at",
    "online",
}

EXTRAPOLATED_SENSOR_KEYS = {
    "from_start_ex",
    "to_finish_ex",
    "gap_ex",
    "gap_chase_ex",
    "gap_average_ex",
    "gap_distance_ex",
}


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def _nested_keys(obj: Any, prefix: str = "") -> set[str]:
    """Return the set of fully-qualified nested key paths of a mapping."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            keys.add(path)
            keys |= _nested_keys(value, path)
    return keys


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
    assert names >= SENSOR_KEYS


def test_extrapolated_sensor_keys_translated() -> None:
    """Each translation file exposes the six extrapolated sensor names."""
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        sensor = _load(name)["entity"]["sensor"]
        assert set(sensor) >= EXTRAPOLATED_SENSOR_KEYS, name


def test_device_tracker_key_translated() -> None:
    """The tracker translation key is present in all translation files."""
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        entity = _load(name)["entity"]
        assert "device_tracker" in entity, name
        assert "tracker" in entity["device_tracker"], name
        assert "name" in entity["device_tracker"]["tracker"], name


def test_de_has_same_toplevel_keys() -> None:
    en = _load("translations/en.json")
    de = _load("translations/de.json")
    assert set(en) == set(de)


def test_full_nested_source_keys_match_across_files() -> None:
    """Compare complete nested source keys across the three translation files.

    Only structural source keys (config, options, entity sensor keys and the
    entity device_tracker key) are compared; the translated leaf *values*
    naturally differ per language.
    """
    strings = _load("strings.json")
    en = _load("translations/en.json")
    de = _load("translations/de.json")

    def structural_keys(data: dict) -> set[str]:
        keys: set[str] = set()
        for section in ("config", "options"):
            keys |= _nested_keys(data.get(section, {}), section)
        entity = data.get("entity", {})
        keys |= _nested_keys(entity.get("sensor", {}), "entity.sensor")
        keys |= _nested_keys(entity.get("device_tracker", {}), "entity.device_tracker")
        return keys

    strings_keys = structural_keys(strings)
    en_keys = structural_keys(en)
    de_keys = structural_keys(de)

    assert strings_keys == en_keys
    assert strings_keys == de_keys


def test_icons_cover_selected_keys() -> None:
    icons = _load("icons.json")["entity"]["sensor"]
    assert {"speed", "from_start", "to_finish", "eta", "gap", "online"} <= set(icons)


def test_icons_cover_extrapolated_keys() -> None:
    icons = _load("icons.json")["entity"]["sensor"]
    assert set(icons) >= EXTRAPOLATED_SENSOR_KEYS
