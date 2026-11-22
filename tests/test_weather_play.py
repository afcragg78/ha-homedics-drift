"""Weather upload, clean, and play: no play_pause, no idle wait, confirm or skip."""

from __future__ import annotations

import asyncio
from pathlib import Path

from custom_components.homedics_drift.const import (
    PATTERN_START_WAIT,
    draw_with_confirm,
    wait_for_reported_pattern,
)


COORDINATOR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "homedics_drift"
    / "coordinator.py"
)


def _coordinator_source() -> str:
    return COORDINATOR.read_text()


def test_upload_and_weather_play_do_not_send_play_pause() -> None:
    """play_pause is a toggle; v1.4.10 used it before upload and broke Clean."""
    source = _coordinator_source()
    upload = source.split("async def async_upload_pattern(", 1)[1].split(
        "async def _async_wait_for_link(", 1
    )[0]
    weather = source.split("async def async_draw_weather(", 1)[1].split(
        "async def async_draw_photo(", 1
    )[0]
    confirm = source.split("async def _async_draw_and_confirm(", 1)[1].split(
        "async def _async_clean_then_play(", 1
    )[0]
    for block in (upload, weather, confirm):
        assert "play_pause(" not in block
        assert "_async_pause_for_upload" not in block
    assert "async def _async_pause_for_upload" not in source
    assert "_async_wait_until_idle" not in source
    assert "UPLOAD_IDLE_WAIT" not in source


def test_a_running_playlist_does_not_block_upload_or_play() -> None:
    """v1.4.6 could draw weather while a playlist was already running."""
    source = _coordinator_source()
    assert "_async_wait_until_idle" not in source
    assert "The table is still drawing. Wait until it stops" not in source
    # Confirmation only waits for the reported pattern id, not for idle.
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    async def sleep(seconds: float) -> None:
        clock["t"] += seconds

    state = {"id": 670, "seq": 0, "drawing": True}

    async def send() -> None:
        # The table can still be mid-playlist when the draw is sent.
        assert state["drawing"] is True
        state["seq"] += 1
        state["id"] = 50002

    async def _run() -> bool:
        return await draw_with_confirm(
            send=send,
            reported_id=lambda: state["id"],
            pattern_id=50002,
            report_seq=lambda: state["seq"],
            timeout=PATTERN_START_WAIT,
            sleep=sleep,
            clock=now,
        )

    assert asyncio.run(_run()) is True
    assert clock["t"] == 0.0
    assert state["id"] == 50002


def test_unconfirmed_clean_falls_through_to_weather_within_45_seconds() -> None:
    """If Clean never starts, play Weather instead of waiting 20 minutes."""
    clock = {"t": 0.0}
    draws: list[int] = []
    played: list[int] = []
    warnings: list[str] = []

    def now() -> float:
        return clock["t"]

    async def sleep(seconds: float) -> None:
        clock["t"] += seconds

    state = {"id": 670, "seq": 0}

    async def send_clean() -> None:
        draws.append(50002)
        state["seq"] += 1
        # Table stays on the playlist.

    async def play_weather() -> bool:
        played.append(71000)
        return True

    async def _run() -> None:
        started = await draw_with_confirm(
            send=send_clean,
            reported_id=lambda: state["id"],
            pattern_id=50002,
            report_seq=lambda: state["seq"],
            timeout=PATTERN_START_WAIT,
            sleep=sleep,
            clock=now,
        )
        if started:
            raise AssertionError("clean should not have been confirmed")
        warnings.append("clean did not start")
        await play_weather()

    asyncio.run(_run())
    assert draws == [50002, 50002]
    assert played == [71000]
    assert warnings == ["clean did not start"]
    assert clock["t"] <= 45
    assert clock["t"] >= 2 * PATTERN_START_WAIT - 0.2


def test_weather_play_is_confirmed_with_one_retry() -> None:
    clock = {"t": 0.0}
    draws: list[int] = []

    def now() -> float:
        return clock["t"]

    async def sleep(seconds: float) -> None:
        clock["t"] += seconds

    state = {"id": 670, "seq": 0}

    async def send() -> None:
        draws.append(71000)
        state["seq"] += 1
        if len(draws) >= 2:
            state["id"] = 71000

    async def _run() -> bool:
        return await draw_with_confirm(
            send=send,
            reported_id=lambda: state["id"],
            pattern_id=71000,
            report_seq=lambda: state["seq"],
            timeout=PATTERN_START_WAIT,
            sleep=sleep,
            clock=now,
        )

    assert asyncio.run(_run()) is True
    assert draws == [71000, 71000]
    assert clock["t"] == PATTERN_START_WAIT


def test_wait_for_reported_pattern_ignores_optimistic_local_ids() -> None:
    """A local _replace is not enough; a later status packet must match."""
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    async def sleep(seconds: float) -> None:
        clock["t"] += seconds

    # seq has not advanced since the command, even if the local id changed.
    async def _run() -> bool:
        return await wait_for_reported_pattern(
            reported_id=lambda: 50002,
            pattern_id=50002,
            report_seq=lambda: 3,
            after_seq=3,
            timeout=1.0,
            sleep=sleep,
            clock=now,
        )

    assert asyncio.run(_run()) is False
    assert clock["t"] == 1.0
