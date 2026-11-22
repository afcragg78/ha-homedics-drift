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
from .const import WEATHER_MAX_POINTS
from .patterns import fit_thr_text

WEATHER_NAME = "Weather"

DEFAULT_WEATHER_UNIT = "auto"
DEFAULT_WEATHER_ROTATION = 0
DEFAULT_WEATHER_AFTER_PATTERN = False
DEFAULT_WEATHER_COOLDOWN_MIN = 30

# Picture names the draw_weather service accepts, in the order the selector shows.
PICTURES = (
    "sunny",
    "partlycloudy",
    "cloudy",
    "hot",
    "cold",
    "clear_night",
    "fog",
    "rain",
    "heavy_rain",
    "thunderstorm",
    "hail",
    "sleet",
    "snow",
    "windy",
    "alert",
)

# Forecast pictures that also carry a gust when the wind is over the threshold.
_WIND_COMBOS = (
    "sunny_wind",
    "rain_wind",
    "heavy_rain_wind",
    "thunderstorm_wind",
    "hail_wind",
    "sleet_wind",
    "snow_wind",
    "fog_wind",
    "hot_wind",
    "cold_wind",
    "alert_wind",
)
DRAWINGS = PICTURES + _WIND_COMBOS

# Home Assistant weather conditions, and the picture each one draws.
# Wind combinations and the hot/cold/alert choices are applied separately.
_CONDITION_MAP = {
    "sunny": "sunny",
    "clear-night": "clear_night",
    "partlycloudy": "partlycloudy",
    "cloudy": "cloudy",
    "fog": "fog",
    "windy": "windy",
    "windy-variant": "windy",
    "exceptional": "cloudy",
    "rainy": "rain",
    "pouring": "heavy_rain",
    "heavy-rain": "heavy_rain",
    "lightning": "thunderstorm",
    "lightning-rainy": "thunderstorm",
    "hail": "hail",
    "rain": "rain",
    "thunderstorm": "thunderstorm",
    "snowy": "snow",
    "snowy-rainy": "sleet",
    "sleet": "sleet",
    "snow": "snow",
    "hot": "hot",
    "cold": "cold",
    "alert": "alert",
    "rain-wind": "rain_wind",
    "heavy-rain-wind": "heavy_rain_wind",
    "thunderstorm-wind": "thunderstorm_wind",
    "hail-wind": "hail_wind",
    "sleet-wind": "sleet_wind",
    "snow-wind": "snow_wind",
    "fog-wind": "fog_wind",
    "hot-wind": "hot_wind",
    "cold-wind": "cold_wind",
    "alert-wind": "alert_wind",
    "sunny-wind": "sunny_wind",
}


class WeatherDesignError(Exception):
    """The forecast cannot be drawn. The table is left as it is."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def map_condition(condition: str) -> str:
    """The picture name for a Home Assistant forecast condition."""
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


def _first_forecast(response: object, entity_id: str) -> dict[str, object]:
    """The first day of a ``weather.get_forecasts`` ``type: daily`` response."""
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
    if not isinstance(first, dict):
        raise WeatherDesignError("The weather entity did not return a daily forecast")
    return first


def forecast_high(response: object, entity_id: str) -> tuple[str, float]:
    """Condition and high from ``weather.get_forecasts`` ``type: daily``."""
    first = _first_forecast(response, entity_id)
    condition = first.get("condition")
    temperature = first.get("temperature")
    if not isinstance(condition, str) or not condition.strip():
        raise WeatherDesignError("The forecast did not include a condition")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise WeatherDesignError("The forecast did not include a high temperature")
    return condition, float(temperature)


def forecast_wind_speed(response: object, entity_id: str) -> float | None:
    """Wind speed on the first forecast day, or None when that day omits it."""
    try:
        first = _first_forecast(response, entity_id)
    except WeatherDesignError:
        return None
    speed = first.get("wind_speed")
    if isinstance(speed, bool) or not isinstance(speed, (int, float)):
        return None
    return float(speed)


# Multiply by these to get m/s. They are Home Assistant's SpeedConverter ratios.
_METERS_PER_SECOND: dict[str, float] = {
    "m/s": 1.0,
    "km/h": 1.0 / 3.6,
    "mph": 1.0 / 2.2369362920544025,
    "kn": 1.852 / 3.6,
    "ft/s": 1.0 / 3.280839895013123,
}
_SPEED_ALIASES = {
    "m/s": "m/s",
    "mps": "m/s",
    "km/h": "km/h",
    "kmh": "km/h",
    "kph": "km/h",
    "mph": "mph",
    "mi/h": "mph",
    "mp/h": "mph",
    "kn": "kn",
    "kt": "kn",
    "knot": "kn",
    "knots": "kn",
    "ft/s": "ft/s",
    "fps": "ft/s",
}

def canonical_speed_unit(unit: object) -> str | None:
    """``mph``, ``km/h``, ``m/s``, ``kn``, or ``ft/s``."""
    if not isinstance(unit, str):
        return None
    return _SPEED_ALIASES.get(unit.strip().lower().replace(" ", ""))


def convert_wind_speed(value: float, source_unit: object, target_unit: str) -> float:
    """Convert a wind speed with Home Assistant's speed converter.

    ``SpeedConverter`` is used when Home Assistant is installed. The same
    ratios are used otherwise, so a test and a running instance agree.
    """
    source = canonical_speed_unit(source_unit)
    target = canonical_speed_unit(target_unit)
    if source is None or target is None:
        raise WeatherDesignError("The wind speed unit is not one this table can convert")
    if source == target:
        return float(value)
    try:
        from homeassistant.util.unit_conversion import SpeedConverter
    except ImportError:
        SpeedConverter = None  # type: ignore[assignment]
    if SpeedConverter is not None:
        return float(SpeedConverter.convert(float(value), source, target))
    meters = float(value) * _METERS_PER_SECOND[source]
    return meters / _METERS_PER_SECOND[target]


def wind_threshold_unit(temperature_preference: object, entity_temperature_unit: object) -> str:
    """``mph`` next to °F, ``km/h`` next to °C. Auto follows the weather entity."""
    asked = (
        temperature_preference.strip().upper()
        if isinstance(temperature_preference, str)
        else "AUTO"
    )
    if asked == "C":
        return "km/h"
    if asked == "F":
        return "mph"
    if _unit_code(entity_temperature_unit) == "C":
        return "km/h"
    return "mph"


def default_wind_threshold(unit: str) -> float:
    """Beaufort 4, a moderate breeze: 15 mph or 25 km/h."""
    return 25.0 if unit == "km/h" else 15.0


def wind_threshold_value(saved: object, unit: str) -> float:
    """The saved threshold, or the Beaufort 4 default when it has never been set."""
    if isinstance(saved, bool) or saved is None:
        return default_wind_threshold(unit)
    try:
        number = float(saved)
    except (TypeError, ValueError):
        return default_wind_threshold(unit)
    if number < 0:
        return 0.0
    if number > 200:
        return 200.0
    return number


def _condition_key(condition: str) -> str:
    key = condition.strip().lower().replace("_", "-")
    if key == "partly-cloudy":
        return "partlycloudy"
    return key


def forecast_low(response: object, entity_id: str) -> float | None:
    """Overnight low on the first forecast day, or None when it is missing."""
    try:
        first = _first_forecast(response, entity_id)
    except WeatherDesignError:
        return None
    low = first.get("templow")
    if isinstance(low, bool) or not isinstance(low, (int, float)):
        return None
    return float(low)


def forecast_probability(response: object, entity_id: str) -> float | None:
    """Precipitation probability, 0–100, or None when the forecast omits it."""
    try:
        first = _first_forecast(response, entity_id)
    except WeatherDesignError:
        return None
    chance = first.get("precipitation_probability")
    if isinstance(chance, bool) or not isinstance(chance, (int, float)):
        return None
    return float(chance)


def temperature_threshold_unit(temperature_preference: object, entity_temperature_unit: object) -> str:
    """``F`` or ``C``. Auto follows the weather entity, and an unknown unit is °F."""
    asked = (
        temperature_preference.strip().upper()
        if isinstance(temperature_preference, str)
        else "AUTO"
    )
    if asked == "C":
        return "C"
    if asked == "F":
        return "F"
    if _unit_code(entity_temperature_unit) == "C":
        return "C"
    return "F"


def default_hot_threshold(unit: str) -> float:
    """90°F or 32°C."""
    return 32.0 if unit == "C" else 90.0


def default_cold_threshold(unit: str) -> float:
    """32°F or 0°C."""
    return 0.0 if unit == "C" else 32.0


def default_heavy_probability() -> float:
    return 70.0


def _saved_number(saved: object, fallback: float, low: float, high: float) -> float:
    if isinstance(saved, bool) or saved is None:
        return fallback
    try:
        number = float(saved)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def hot_threshold_value(saved: object, unit: str) -> float:
    return _saved_number(saved, default_hot_threshold(unit), -40, 140)


def cold_threshold_value(saved: object, unit: str) -> float:
    return _saved_number(saved, default_cold_threshold(unit), -80, 80)


def heavy_probability_value(saved: object) -> float:
    return _saved_number(saved, default_heavy_probability(), 0, 100)


def alert_active(state: object) -> bool:
    """A binary sensor that is on, or a sensor whose number is above zero."""
    if not isinstance(state, str):
        return False
    text = state.strip().lower()
    if text in {"on", "true", "yes"}:
        return True
    if text in {"off", "false", "no", "unknown", "unavailable", "none", ""}:
        return False
    try:
        return float(text) > 0
    except ValueError:
        return False


_FULL_WIND = frozenset({"sunny", "partlycloudy", "cloudy", "clear_night", "windy"})
_PRECIPITATION = frozenset(
    {
        "lightning",
        "lightning-rainy",
        "thunderstorm",
        "hail",
        "snowy-rainy",
        "sleet",
        "snowy",
        "snow",
        "pouring",
        "heavy-rain",
        "rainy",
        "rain",
    }
)


def choose_picture(
    *,
    condition: str,
    wind_speed: float | None,
    wind_threshold: float,
    temperature_high: float | None,
    temperature_low: float | None,
    hot_threshold: float,
    cold_threshold: float,
    precipitation_probability: float | None,
    heavy_threshold: float,
    alert: bool,
) -> str:
    """Which picture to draw for one forecast day.

    Order, before the wind is added: alert, storm, hail, sleet, snow, heavy
    rain, rain, fog, hot or cold, then the fair-weather sky. Wind at or above
    the threshold replaces a fair sky with the full gust picture. On every
    other symbol it is drawn beside that symbol, so the wind stays visible.
    """
    key = _condition_key(condition)
    if alert:
        base = "alert"
    elif key in {"lightning", "lightning-rainy", "thunderstorm"}:
        base = "thunderstorm"
    elif key == "hail":
        base = "hail"
    elif key in {"snowy-rainy", "sleet"}:
        base = "sleet"
    elif key in {"snowy", "snow"}:
        base = "snow"
    elif key in {"pouring", "heavy-rain"} or (
        precipitation_probability is not None
        and float(precipitation_probability) >= float(heavy_threshold)
    ):
        base = "heavy_rain"
    elif key in {"rainy", "rain"}:
        base = "rain"
    elif key == "fog":
        base = "fog"
    elif (
        key not in _PRECIPITATION
        and key != "fog"
        and temperature_high is not None
        and float(temperature_high) >= float(hot_threshold)
    ):
        base = "hot"
    elif (
        key in {"sunny", "clear-night", "partlycloudy", "cloudy"}
        and temperature_low is not None
        and float(temperature_low) <= float(cold_threshold)
    ):
        base = "cold"
    else:
        base = map_condition(condition)
    if wind_speed is None or float(wind_speed) < float(wind_threshold):
        return base
    if base in _FULL_WIND:
        return "windy"
    return f"{base}_wind"


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

    Theta starts as ``atan2(y, x)``. Each later point is unwrapped against the
    previous theta so the step stays within π. The table interpolates linearly
    in theta and rho, and a raw 2π jump where the path crosses the negative
    x-axis would be drawn as a full orbit. Rho is the distance from the centre,
    clamped to 0..1. ``patterns.wire_point`` then uses the same millidegrees as
    Drifted's ``.txt`` writer, so a rotation of 0 matches that layout.
    """
    lines: list[str] = []
    previous: float | None = None
    for x, y in points:
        theta = math.atan2(y, x)
        if previous is not None:
            while theta - previous > math.pi:
                theta -= 2 * math.pi
            while theta - previous < -math.pi:
                theta += 2 * math.pi
        previous = theta
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
    return fit_thr_text(xy_to_thr(path), max_points=WEATHER_MAX_POINTS)


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
    alert = data.get("weather_alert_entity", "")
    if not isinstance(alert, str):
        alert = ""
    return {
        "weather_entity": entity.strip(),
        "weather_unit": unit,
        "weather_rotation": _as_int(data.get("weather_rotation"), DEFAULT_WEATHER_ROTATION, 0, 359),
        "weather_after_pattern": _as_bool(
            data.get("weather_after_pattern"), DEFAULT_WEATHER_AFTER_PATTERN
        ),
        "weather_cooldown_min": cooldown_minutes(data.get("weather_cooldown_min")),
        "weather_wind_threshold": data.get("weather_wind_threshold"),
        "weather_hot_threshold": data.get("weather_hot_threshold"),
        "weather_cold_threshold": data.get("weather_cold_threshold"),
        "weather_heavy_probability": data.get("weather_heavy_probability"),
        "weather_alert_entity": alert.strip(),
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
