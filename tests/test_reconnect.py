"""A dropped link waits, then one reconnect runs. An advert skips the wait."""

from __future__ import annotations

import asyncio

from custom_components.homedics_drift.reconnect import (
    DISCONNECTED_MESSAGE,
    LinkWatch,
    backoff_seconds,
)


def test_backoff_starts_at_two_seconds_and_caps_at_sixty() -> None:
    assert backoff_seconds(0, roll=0.5) == 2.0
    assert backoff_seconds(1, roll=0.5) == 4.0
    assert backoff_seconds(2, roll=0.5) == 8.0
    assert backoff_seconds(8, roll=0.5) == 60.0
    low = backoff_seconds(0, roll=0.0)
    high = backoff_seconds(0, roll=1.0)
    assert low == 1.6
    assert high == 2.4
    assert backoff_seconds(8, roll=0.0) == 48.0
    # The 60s cap is applied first, then jitter can spread it to 72s.
    assert backoff_seconds(8, roll=1.0) == 72.0
    assert backoff_seconds(20, roll=1.0) == 72.0


def test_one_attempt_at_a_time_and_advert_does_not_stack() -> None:
    watch = LinkWatch()
    assert watch.begin() is True
    assert watch.begin() is False
    assert watch.advertisement() is False
    assert watch.wake is False
    watch.mark_up()
    assert watch.connected is True
    assert watch.unavailable is False
    assert watch.busy is True
    delay = watch.mark_down(roll=0.5)
    assert delay == 2.0
    assert watch.connected is False
    assert watch.unavailable is True
    assert watch.busy is False
    assert watch.advertisement() is False
    watch.earliest_wake = 0
    assert watch.advertisement() is True
    assert watch.take_wake() is True
    assert watch.take_wake() is False


def test_a_command_while_down_asks_for_one_reconnect() -> None:
    watch = LinkWatch()
    assert watch.begin()
    watch.mark_down(roll=0.5)
    assert watch.command_while_down() == DISCONNECTED_MESSAGE
    assert watch.take_wake() is True
    assert watch.begin()
    assert watch.command_while_down() == DISCONNECTED_MESSAGE
    assert watch.wake is False


def test_disconnect_then_advertisement_reconnects_without_a_second_client() -> None:
    asyncio.run(_dropped_link())


async def _dropped_link() -> None:
    """The first session drops, an advert skips the rest of the wait, the next one holds."""
    watch = LinkWatch()
    sessions = 0
    sleeps: list[float] = []

    async def session() -> None:
        nonlocal sessions
        sessions += 1
        watch.mark_up()
        if sessions == 1:
            raise ConnectionError("Bluetooth link dropped")

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)
        watch.earliest_wake = 0
        watch.advertisement()

    assert watch.begin()
    try:
        await session()
    except ConnectionError as err:
        assert "dropped" in str(err)
        delay = watch.mark_down(roll=0.5)
    assert delay == 2.0
    assert watch.unavailable is True
    await sleeper(delay)
    assert watch.take_wake() is True
    assert sleeps == [2.0]
    assert watch.begin() is True
    assert watch.begin() is False
    await session()
    assert watch.connected is True
    assert sessions == 2
