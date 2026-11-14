"""Forecast pictures for the sand table.

The shapes and digits are Josh Lannin's Drifted design, vendored in
``weather_design.py`` (MIT, Copyright (c) 2026 Altimix LLC,
https://github.com/joshlannin/drifted/blob/main/designs/weather.py). This module
turns that drawing into a ``.thr`` path and decides when Auto Weather should run.
It does not import Home Assistant.
"""

from __future__ import annotations

import math

from . import weather_design

WEATHER_NAME = "Weather"

DEFAULT_WEATHER_UNIT = "auto"
DEFAULT_WEATHER_ROTATION = 0
DEFAULT_WEATHER_AFTER_PATTERN = False
DEFAULT_WEATHER_COOLDOWN_MIN = 30

# Home Assistant weather conditions, grouped the way the four pictures read.
_CONDITION_MAP = {
    "sunny": "sunny",
    "clear-night": "sunny",
    "partlycloudy": "cloudy",
    "cloudy": "cloudy",
    "fog": "cloudy",
    "windy": "cloudy",
    "windy-variant": "cloudy",
    "exceptional": "cloudy",
    "rainy": "rain",
    "pouring": "rain",
    "lightning": "rain",
    "lightning-rainy": "rain",
    "hail": "rain",
    "rain": "rain",
    "snowy": "snow",
    "snowy-rainy": "snow",
    "snow": "snow",
}


class WeatherDesignError(Exception):
    """The forecast cannot be drawn. The table is left as it is."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def map_condition(condition: str) -> str:
    """One of sunny, cloudy, rain, or snow."""
    key = condition.strip().lower().replace("_", "-")
    if key == "partly-cloudy":
        key = "partlycloudy"
    mapped = _CONDITION_MAP.get(key)
    if mapped is None:
        raise WeatherDesignError(
            f"The forecast condition {condition!r} is not one this table can draw"
        )
    return mapped


def _unit_code(unit: object) -> str | None:
    """``C`` or ``F`` from a weather entity's temperature unit, or None."""
    if not isinstance(unit, str):
        return None
    token = unit.strip().upper().replace("°", "").replace(" ", "")
    if token in {"C", "CELSIUS"}:
        return "C"
    if token in {"F", "FAHRENHEIT"}:
        return "F"
    return None


def convert_temperature(value: float, source_unit: object, preference: object) -> int:
    """The integer high the digits should show, in the unit the user asked for.

    ``auto`` keeps the weather entity's unit. ``F`` or ``C`` converts when the
    entity reports the other one. The result has to fit the design, -99..199.
    """
    source = _unit_code(source_unit)
    asked = preference.strip().upper() if isinstance(preference, str) else "AUTO"
    if asked in {"F", "C"}:
        target = asked
    else:
        target = source
    number = float(value)
    if source == "C" and target == "F":
        number = number * 9.0 / 5.0 + 32.0
    elif source == "F" and target == "C":
        number = (number - 32.0) * 5.0 / 9.0
    rounded = int(round(number))
    if rounded < -99 or rounded > 199:
        raise WeatherDesignError(f"temperature {rounded} is outside -99..199")
    return rounded


def forecast_high(response: object, entity_id: str) -> tuple[str, float]:
    """Condition and high from ``weather.get_forecasts`` ``type: daily``."""
    if not isinstance(response, dict):
        raise WeatherDesignError("The weather entity did not return a daily forecast")
    block = response.get(entity_id)
    if not isinstance(block, dict) and len(response) == 1:
        only = next(iter(response.values()))
        block = only if isinstance(only, dict) else None
    forecast = block.get("forecast") if isinstance(block, dict) else None
    if not isinstance(forecast, list) or not forecast or not isinstance(forecast[0], dict):
        raise WeatherDesignError("The weather entity did not return a daily forecast")
    first = forecast[0]
    condition = first.get("condition")
    temperature = first.get("temperature")
    if not isinstance(condition, str) or not condition.strip():
        raise WeatherDesignError("The forecast did not include a condition")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise WeatherDesignError("The forecast did not include a high temperature")
    return condition, float(temperature)


def rotate_xy(points: list[tuple[float, float]], degrees: float) -> list[tuple[float, float]]:
    """Turn a picture counter-clockwise, the same rotation as Drifted's ``write``."""
    angle = math.radians(float(degrees))
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return [
        (x * cos_a - y * sin_a, x * sin_a + y * cos_a)
        for x, y in points
    ]


def xy_to_thr(points: list[tuple[float, float]]) -> str:
    """Cartesian points to a Sandify ``.thr`` document.

    Theta is ``atan2(y, x)`` in radians. Rho is the distance from the centre,
    clamped to 0..1. ``patterns.wire_point`` then uses the same millidegrees as
    Drifted's ``.txt`` writer, so a rotation of 0 matches that layout.
    """
    lines: list[str] = []
    for x, y in points:
        theta = math.atan2(y, x)
        rho = min(1.0, max(0.0, math.hypot(x, y)))
        lines.append(f"{theta:.6f} {rho:.6f}")
    return "\n".join(lines) + "\n"


def render_weather_thr(
    condition: str,
    temperature: int,
    rotation: float,
    *,
    panel_only: bool,
) -> str:
    """Build the picture off the event loop. ``panel_only`` redraws the digits."""
    name = map_condition(condition)
    value = int(temperature)
    if not -99 <= value <= 199:
        raise WeatherDesignError(f"temperature {value} is outside -99..199")
    if panel_only:
        path, _cap = weather_design.panel(value)
    else:
        path, _cap = weather_design.build(name, value)
    path = weather_design.densify(path)
    path = rotate_xy(path, rotation)
    return xy_to_thr(path)


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
    if value is None:
        return default
    return default


def _as_int(value: object, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        try:
            number = int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default
    return max(low, min(high, number))


def rotation_degrees(value: object) -> float:
    """0..359 degrees counter-clockwise. Anything else is 0."""
    return float(_as_int(value, DEFAULT_WEATHER_ROTATION, 0, 359))


def cooldown_minutes(value: object) -> int:
    """Minutes between automatic weather drawings. Default 30."""
    return _as_int(value, DEFAULT_WEATHER_COOLDOWN_MIN, 0, 24 * 60)


def weather_options_from(options: dict[str, object] | None) -> dict[str, object]:
    """Saved options, with the defaults filled in for anything not set yet."""
    data = options or {}
    unit = data.get("weather_unit", DEFAULT_WEATHER_UNIT)
    if not isinstance(unit, str) or unit not in {"auto", "F", "C"}:
        unit = DEFAULT_WEATHER_UNIT
    entity = data.get("weather_entity", "")
    if not isinstance(entity, str):
        entity = ""
    return {
        "weather_entity": entity.strip(),
        "weather_unit": unit,
        "weather_rotation": _as_int(data.get("weather_rotation"), DEFAULT_WEATHER_ROTATION, 0, 359),
        "weather_after_pattern": _as_bool(
            data.get("weather_after_pattern"), DEFAULT_WEATHER_AFTER_PATTERN
        ),
        "weather_cooldown_min": cooldown_minutes(data.get("weather_cooldown_min")),
    }


def initial_auto_weather(restored: str | None, option: object) -> bool:
    """Whether Auto Weather is on after a restart.

    A restored on or off wins. The first time the switch exists, the
    ``weather_after_pattern`` option is the starting value, and that defaults
    to off.
    """
    if restored == "on":
        return True
    if restored == "off":
        return False
    return _as_bool(option, DEFAULT_WEATHER_AFTER_PATTERN)


def temperature_panel_only(
    *,
    condition: str,
    temperature: int,
    last_condition: str,
    last_temperature: int | None,
    weather_pattern_id: int | None,
    current_pattern_id: int | None,
    drawing: bool,
) -> bool:
    """Redraw only the digits when the high changed and Weather is still showing.

    The ball has to be idle. Replacing the pattern that is drawing is refused
    by the same id check as any other upload.
    """
    if drawing or weather_pattern_id is None or current_pattern_id != weather_pattern_id:
        return False
    if not last_condition or last_temperature is None:
        return False
    return condition == last_condition and temperature != last_temperature


def auto_weather_allowed(
    *,
    auto_on: bool,
    session_on: bool,
    draw_active: bool,
    finished_pattern_id: int,
    weather_pattern_id: int | None,
    clean_pattern_ids: set[int],
    now: float,
    last_weather_at: float | None,
    cooldown_min: float,
) -> bool:
    """True when a finished design should be followed by the forecast."""
    if not auto_on or not session_on or draw_active:
        return False
    if finished_pattern_id <= 0:
        return False
    if weather_pattern_id is not None and finished_pattern_id == weather_pattern_id:
        return False
    if finished_pattern_id in clean_pattern_ids:
        return False
    if last_weather_at is not None and cooldown_min > 0:
        if now - last_weather_at < cooldown_min * 60.0:
            return False
    return True


class DesignFinish:
    """A design that just finished, from the status the table already pushes.

    Two signals, and either one is enough: progress reached about 100 and the
    pattern id then changed, or drawing went from on to off at 99% or more.
    Nothing here polls.
    """

    def __init__(self) -> None:
        self.pattern_id = 0
        self.progress = 0.0
        self.drawing = False
        self.peaked = False
        self.reported = False

    def observe(
        self,
        *,
        session_on: bool,
        drawing: bool,
        progress: float,
        pattern_id: int,
    ) -> int | None:
        """The pattern id that finished, or None. Power off never reports one."""
        finished: int | None = None
        changed = pattern_id > 0 and pattern_id != self.pattern_id
        if changed:
            if self.peaked and self.pattern_id > 0 and not self.reported:
                finished = self.pattern_id
            # The new design has not finished. A stale 100% is not a finish yet.
            self.peaked = False
            self.reported = False
        elif (
            self.drawing
            and not drawing
            and self.pattern_id > 0
            and not self.reported
            and (self.progress >= 0.99 or progress >= 0.99)
        ):
            finished = self.pattern_id
            self.reported = True
        if not changed and pattern_id > 0 and progress < 0.95:
            self.peaked = False
        elif not changed and pattern_id > 0 and progress >= 0.99:
            self.peaked = True
        if pattern_id > 0:
            self.pattern_id = pattern_id
        self.drawing = drawing
        self.progress = progress
        if not session_on:
            return None
        return finished
