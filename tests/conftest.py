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
