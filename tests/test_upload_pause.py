"""A running playlist is paused before upload instead of waiting to go idle."""

from __future__ import annotations

import asyncio
from pathlib import Path

from custom_components.homedics_drift.const import (
    UPLOAD_PAUSE_SETTLE,
    UPLOAD_PAUSE_WAIT,
    UploadPauseAborted,
    should_pause_for_upload,
    wait_for_pause_to_take,
)
from custom_components.homedics_drift.protocol import CMD_ACTION, play_pause


def test_a_running_playlist_should_be_paused_before_upload() -> None:
    """The table often loops a stored playlist, so it is never naturally idle."""
    assert should_pause_for_upload(drawing=True, progress=0.28) is True
    assert should_pause_for_upload(drawing=True, progress=0.0) is True
    assert should_pause_for_upload(drawing=True, progress=None) is True
    assert should_pause_for_upload(drawing=False, progress=0.28) is False
    assert should_pause_for_upload(drawing=False, progress=None) is False
    # Stop after can leave drawing true at the end; toggling would resume it.
    assert should_pause_for_upload(drawing=True, progress=0.99) is False
    assert should_pause_for_upload(drawing=True, progress=1.0) is False


def test_pause_before_upload_waits_seconds_not_minutes() -> None:
    assert 0 < UPLOAD_PAUSE_SETTLE <= UPLOAD_PAUSE_WAIT
    assert UPLOAD_PAUSE_WAIT <= 10


def test_upload_path_pauses_instead_of_waiting_for_natural_idle() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "homedics_drift"
        / "coordinator.py"
    ).read_text()
    assert "async def _async_pause_for_upload" in source
    assert "await self.async_send(play_pause())" in source
    assert "await self._async_pause_for_upload()" in source
    assert "_async_wait_until_idle" not in source
    assert "UPLOAD_IDLE_WAIT" not in source


def test_wait_after_pause_returns_quickly_once_the_table_is_still() -> None:
    sleeps: list[float] = []
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    async def _run() -> None:
        await wait_for_pause_to_take(
            is_moving=lambda: False,
            is_shut_down=lambda: False,
            is_powered=lambda: True,
            settle=1.0,
            timeout=5.0,
            sleep=fake_sleep,
            clock=now,
        )

    asyncio.run(_run())
    assert 1.0 <= clock["t"] <= 1.4
    assert sum(sleeps) <= 1.4
    assert clock["t"] < 15 * 60


def test_wait_after_pause_does_not_block_on_a_playlist_that_never_idles() -> None:
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    async def fake_sleep(seconds: float) -> None:
        clock["t"] += seconds

    async def _run() -> None:
        await wait_for_pause_to_take(
            is_moving=lambda: True,
            is_shut_down=lambda: False,
            is_powered=lambda: True,
            settle=1.0,
            timeout=5.0,
            sleep=fake_sleep,
            clock=now,
        )

    asyncio.run(_run())
    assert 5.0 <= clock["t"] <= 5.4
    assert clock["t"] < 15 * 60


def test_wait_after_pause_stops_if_power_goes_off() -> None:
    async def _run() -> None:
        await wait_for_pause_to_take(
            is_moving=lambda: True,
            is_shut_down=lambda: False,
            is_powered=lambda: False,
            settle=1.0,
            timeout=5.0,
            sleep=lambda _s: None,
            clock=lambda: 0.0,
        )

    try:
        asyncio.run(_run())
    except UploadPauseAborted as err:
        assert err.reason == "power_off"
    else:
        raise AssertionError("expected UploadPauseAborted")


def test_play_pause_packet_is_the_command_the_player_already_uses() -> None:
    packet = play_pause()
    assert packet.command == CMD_ACTION
    assert packet.action == 3
