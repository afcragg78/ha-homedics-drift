"""The path endpoint names the weather view rotation for the live card."""

from __future__ import annotations

import sys
import types

from custom_components.homedics_drift.patterns import PatternLibrary, PatternRecord


def _install_fakes() -> None:
    aiohttp = types.ModuleType("aiohttp")
    aiohttp.web = types.ModuleType("aiohttp.web")
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []  # type: ignore[attr-defined]
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    http_mod = types.ModuleType("homeassistant.components.http")

    class HomeAssistantView:
        pass

    http_mod.HomeAssistantView = HomeAssistantView
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    helpers.device_registry = device_registry
    for name, module in {
        "aiohttp": aiohttp,
        "aiohttp.web": aiohttp.web,
        "homeassistant": homeassistant,
        "homeassistant.components": components,
        "homeassistant.components.http": http_mod,
        "homeassistant.core": core,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.device_registry": device_registry,
    }.items():
        sys.modules.setdefault(name, module)


def _http():
    _install_fakes()
    sys.modules.pop("custom_components.homedics_drift.http", None)
    from custom_components.homedics_drift import http

    return http


class _Data:
    def __init__(self, pattern_id: int) -> None:
        self.pattern_id = pattern_id


class _Coordinator:
    def __init__(self, pattern_id: int, library: PatternLibrary, rotation: object, points) -> None:
        self.data = _Data(pattern_id)
        self.library = library
        self.config_entry = types.SimpleNamespace(options={"weather_rotation": rotation})
        self._points = points

    def known_path(self, pattern_id: int):
        assert pattern_id == self.data.pattern_id
        return self._points


def _library(weather_id: int | None) -> PatternLibrary:
    records = {
        50001: PatternRecord(50001, "Spiral", "0 0\n1 1\n", source="upload"),
    }
    if weather_id is not None:
        records[weather_id] = PatternRecord(weather_id, "Weather", "0 0\n1 1\n", source="weather")
    return PatternLibrary(records=records)


def test_weather_path_includes_the_configured_view_rotation() -> None:
    http = _http()
    points = [[0.0, 0.2], [1.2, 0.4]]
    body = http.path_payload(_Coordinator(50110, _library(50110), 270, points))
    assert body == {"pattern_id": 50110, "points": points, "view_rotation": 270.0}

    stored = http.path_payload(_Coordinator(50110, _library(50110), "270", points))
    assert stored["view_rotation"] == 270.0

    unset = http.path_payload(_Coordinator(50110, _library(50110), "sideways", points))
    assert unset["view_rotation"] == 0.0


def test_other_patterns_omit_view_rotation() -> None:
    http = _http()
    points = [[0.0, 1.0], [1.0, 0.5]]
    spiral = http.path_payload(_Coordinator(50001, _library(50110), 270, points))
    assert spiral == {"pattern_id": 50001, "points": points}
    assert "view_rotation" not in spiral

    missing = http.path_payload(_Coordinator(50001, _library(None), 270, points))
    assert "view_rotation" not in missing

    idle = http.path_payload(_Coordinator(0, _library(50110), 270, points))
    assert idle == {"pattern_id": 0, "points": None}
    assert "view_rotation" not in idle

    assert http.path_payload(None) == {"pattern_id": 0, "points": None}
