"""Weather pictures, forecast mapping, and when Auto Weather should run."""

from __future__ import annotations

import math

import pytest

from custom_components.homedics_drift.patterns import (
    MAX_POINTS,
    PatternLibrary,
    parse_thr,
    thr_to_wire,
    wire_point,
)
from custom_components.homedics_drift.weather import (
    DesignFinish,
    WeatherDesignError,
    auto_weather_allowed,
    convert_temperature,
    forecast_high,
    initial_auto_weather,
    map_condition,
    render_weather_thr,
    rotate_xy,
    temperature_panel_only,
    weather_options_from,
    xy_to_thr,
)
from custom_components.homedics_drift.weather_design import build


@pytest.mark.parametrize(
    ("condition", "picture"),
    [
        ("sunny", "sunny"),
        ("clear-night", "sunny"),
        ("partlycloudy", "cloudy"),
        ("cloudy", "cloudy"),
        ("fog", "cloudy"),
        ("windy", "cloudy"),
        ("windy-variant", "cloudy"),
        ("exceptional", "cloudy"),
        ("rainy", "rain"),
        ("pouring", "rain"),
        ("lightning", "rain"),
        ("lightning-rainy", "rain"),
        ("hail", "rain"),
        ("snowy", "snow"),
        ("snowy-rainy", "snow"),
        ("Sunny", "sunny"),
        ("rain", "rain"),
        ("snow", "snow"),
    ],
)
def test_forecast_conditions_use_four_pictures(condition: str, picture: str) -> None:
    assert map_condition(condition) == picture


def test_unknown_condition_is_refused() -> None:
    with pytest.raises(WeatherDesignError):
        map_condition("volcanic")


def test_daily_forecast_uses_the_first_high() -> None:
    condition, temperature = forecast_high(
        {"weather.home": {"forecast": [{"condition": "rainy", "temperature": 18.5, "templow": 9}]}},
        "weather.home",
    )
    assert condition == "rainy"
    assert temperature == 18.5


def test_auto_keeps_the_entity_unit_and_f_or_c_converts() -> None:
    assert convert_temperature(72, "°F", "auto") == 72
    assert convert_temperature(20, "°C", "auto") == 20
    assert convert_temperature(0, "°C", "F") == 32
    assert convert_temperature(20, "C", "F") == 68
    assert convert_temperature(32, "°F", "C") == 0
    assert convert_temperature(68, "fahrenheit", "C") == 20
    assert convert_temperature(20.6, "°C", "C") == 21
    # Same unit is not converted, whichever way the user asked.
    assert convert_temperature(70, "°F", "F") == 70


def test_temperature_outside_the_design_is_refused() -> None:
    with pytest.raises(WeatherDesignError):
        convert_temperature(200, "°C", "F")


def test_rotation_is_counter_clockwise_and_zero_matches_the_txt_writer() -> None:
    assert rotate_xy([(1.0, 0.0)], 90)[0] == pytest.approx((0.0, 1.0))
    assert rotate_xy([(1.0, 0.0)], 0)[0] == pytest.approx((1.0, 0.0))
    x, y = 0.3, -0.4
    theta, rho = parse_thr(xy_to_thr([(x, y)]))[0]
    assert theta == pytest.approx(math.atan2(y, x))
    assert rho == pytest.approx(math.hypot(x, y))
    milli = round(math.degrees(math.atan2(y, x)) * 1000) % 360000
    wire_theta, wire_rho = wire_point(theta, rho)
    assert wire_theta * 6 == milli
    assert wire_rho * 2 == round(min(1.0, math.hypot(x, y)) * 100000)
    # A point past the rim is clamped. The angle is unchanged.
    outside = parse_thr(xy_to_thr([(2.0, 0.0)]))[0]
    assert outside[1] == pytest.approx(1.0)
    assert outside[0] == pytest.approx(0.0)
    # One point from the real picture, rotation 0, same millidegrees as write().
    path, _cap = build("sunny", 72)
    sample = next(point for point in path if math.hypot(*point) > 0.2)
    turned = rotate_xy([sample], 0)[0]
    polar = parse_thr(xy_to_thr([turned]))[0]
    writer = round(math.degrees(math.atan2(sample[1], sample[0])) * 1000) % 360000
    assert wire_point(*polar)[0] * 6 == writer


@pytest.mark.parametrize("condition", ["sunny", "cloudy", "rain", "snow"])
def test_each_picture_fits_on_the_table(condition: str) -> None:
    text = render_weather_thr(condition, 72, 0, panel_only=False)
    wire = thr_to_wire(text)
    assert 10_000 < len(wire) < MAX_POINTS


def test_temperature_panel_is_shorter_than_the_whole_picture() -> None:
    full = len(thr_to_wire(render_weather_thr("sunny", 72, 0, panel_only=False)))
    panel = len(thr_to_wire(render_weather_thr("sunny", 75, 0, panel_only=True)))
    assert 0 < panel < full
    assert panel < MAX_POINTS


def test_options_default_to_auto_unit_no_rotation_and_weather_off() -> None:
    assert weather_options_from({}) == {
        "weather_entity": "",
        "weather_unit": "auto",
        "weather_rotation": 0,
        "weather_after_pattern": False,
        "weather_cooldown_min": 30,
    }
    assert weather_options_from({"weather_rotation": 400, "weather_unit": "Kelvin"}) == {
        "weather_entity": "",
        "weather_unit": "auto",
        "weather_rotation": 359,
        "weather_after_pattern": False,
        "weather_cooldown_min": 30,
    }


def test_switch_remembers_on_or_off_and_the_option_is_only_the_first_value() -> None:
    assert initial_auto_weather(None, False) is False
    assert initial_auto_weather(None, True) is True
    assert initial_auto_weather("on", False) is True
    assert initial_auto_weather("off", True) is False
    assert initial_auto_weather("unknown", False) is False
    assert initial_auto_weather("unavailable", True) is True


def test_last_weather_time_is_stored_with_the_library() -> None:
    library = PatternLibrary()
    library.last_weather_at = 1_700_000_000.0
    library.last_weather_condition = "rain"
    library.last_weather_temperature = 48
    restored = PatternLibrary.from_dict(library.to_dict())
    assert restored.last_weather_at == 1_700_000_000.0
    assert restored.last_weather_condition == "rain"
    assert restored.last_weather_temperature == 48
    blank = PatternLibrary.from_dict({"records": [], "clean_before": False})
    assert blank.last_weather_at is None


def _allow(**overrides: object) -> bool:
    values: dict[str, object] = {
        "auto_on": True,
        "session_on": True,
        "draw_active": False,
        "finished_pattern_id": 12,
        "weather_pattern_id": 50010,
        "clean_pattern_ids": {50000},
        "now": 10_000.0,
        "last_weather_at": None,
        "cooldown_min": 30,
    }
    values.update(overrides)
    return auto_weather_allowed(**values)  # type: ignore[arg-type]


def test_auto_weather_skips_power_off_busy_weather_clean_and_cooldown() -> None:
    assert _allow() is True
    assert _allow(auto_on=False) is False
    assert _allow(session_on=False) is False
    assert _allow(draw_active=True) is False
    assert _allow(finished_pattern_id=50010) is False
    assert _allow(finished_pattern_id=50000) is False
    assert _allow(last_weather_at=10_000.0 - 29 * 60) is False
    assert _allow(last_weather_at=10_000.0 - 31 * 60) is True
    assert _allow(last_weather_at=None) is True


def test_a_finished_design_is_progress_then_a_new_pattern_or_drawing_stopping() -> None:
    watch = DesignFinish()
    assert watch.observe(session_on=True, drawing=True, progress=0.4, pattern_id=3) is None
    assert watch.observe(session_on=True, drawing=True, progress=1.0, pattern_id=3) is None
    assert watch.observe(session_on=True, drawing=True, progress=0.1, pattern_id=8) == 3
    assert watch.observe(session_on=True, drawing=True, progress=0.2, pattern_id=8) is None

    stopped = DesignFinish()
    assert stopped.observe(session_on=True, drawing=True, progress=0.5, pattern_id=4) is None
    assert stopped.observe(session_on=True, drawing=True, progress=0.995, pattern_id=4) is None
    assert stopped.observe(session_on=True, drawing=False, progress=0.995, pattern_id=4) == 4
    assert stopped.observe(session_on=True, drawing=False, progress=0.995, pattern_id=4) is None

    early = DesignFinish()
    assert early.observe(session_on=True, drawing=True, progress=0.5, pattern_id=4) is None
    assert early.observe(session_on=True, drawing=False, progress=0.5, pattern_id=4) is None

    jumped = DesignFinish()
    assert jumped.observe(session_on=True, drawing=True, progress=0.4, pattern_id=4) is None
    assert jumped.observe(session_on=True, drawing=False, progress=1.0, pattern_id=4) == 4

    powered = DesignFinish()
    assert powered.observe(session_on=True, drawing=True, progress=1.0, pattern_id=4) is None
    assert powered.observe(session_on=False, drawing=False, progress=1.0, pattern_id=4) is None


def test_digits_only_when_the_high_changed_and_weather_is_idle_on_the_sand() -> None:
    assert temperature_panel_only(
        condition="sunny",
        temperature=75,
        last_condition="sunny",
        last_temperature=72,
        weather_pattern_id=50010,
        current_pattern_id=50010,
        drawing=False,
    )
    assert not temperature_panel_only(
        condition="rain",
        temperature=75,
        last_condition="sunny",
        last_temperature=72,
        weather_pattern_id=50010,
        current_pattern_id=50010,
        drawing=False,
    )
    assert not temperature_panel_only(
        condition="sunny",
        temperature=75,
        last_condition="sunny",
        last_temperature=72,
        weather_pattern_id=50010,
        current_pattern_id=50010,
        drawing=True,
    )
    assert not temperature_panel_only(
        condition="sunny",
        temperature=72,
        last_condition="sunny",
        last_temperature=72,
        weather_pattern_id=50010,
        current_pattern_id=50010,
        drawing=False,
    )
