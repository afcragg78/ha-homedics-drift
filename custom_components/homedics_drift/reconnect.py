"""When a dropped Drift link should be tried again.

The Bluetooth loop uses this so a retry cannot start while one is already
running, and so an advertisement or a command can skip the wait without
turning that wait into a tight loop.
"""

from __future__ import annotations

import time

DISCONNECTED_MESSAGE = "Drift table is not connected. Reconnecting."
# Advertisements closer together than this must not start another attempt.
ADVERT_GAP: float = 2.0


def backoff_seconds(
    attempt: int,
    *,
    start: float = 2.0,
    cap: float = 60.0,
    jitter: float = 0.2,
    roll: float | None = None,
) -> float:
    """Seconds to wait. Attempt 0 is about 2s, then it doubles, and it stops at 60s.

    ``roll`` is 0..1. It spreads the delay by ``jitter`` on either side so
    many tables do not retry on the same instant. The result stays positive.
    """
    step = max(0, int(attempt))
    base = min(cap, start * (2**step))
    if roll is None:
        import random

        roll = random.random()
    fraction = min(1.0, max(0.0, float(roll)))
    return max(0.05, base * (1.0 + (fraction * 2.0 - 1.0) * jitter))


class LinkWatch:
    """Connected, busy, and the next delay. No sockets."""

    def __init__(self) -> None:
        self.connected = False
        self.busy = False
        self.unavailable = False
        self.wake = False
        self.attempt = 0
        self.earliest_wake = 0.0

    def begin(self) -> bool:
        """True when this caller may open the link. A second caller must wait."""
        if self.busy:
            return False
        self.busy = True
        return True

    def mark_up(self) -> None:
        """The GATT connection is open. The attempt is still busy until it ends."""
        self.connected = True
        self.unavailable = False
        self.attempt = 0
        self.wake = False

    def mark_down(self, *, roll: float | None = None) -> float:
        """The link ended. Return the backoff, and forget any poke from mid-connect."""
        self.connected = False
        self.busy = False
        self.unavailable = True
        self.wake = False
        delay = backoff_seconds(self.attempt, roll=roll)
        self.attempt += 1
        self.earliest_wake = time.monotonic() + ADVERT_GAP
        return delay

    def advertisement(self) -> bool:
        """A fresh advert while we are waiting. Ignored during an attempt.

        Ads in the first two seconds after a failure are ignored so a table
        that keeps advertising cannot spin the reconnect loop.
        """
        if self.connected or self.busy:
            return False
        if time.monotonic() < self.earliest_wake:
            return False
        self.wake = True
        return True

    def command_while_down(self) -> str:
        """The sentence shown to the user. Also asks the waiter to try now."""
        if not self.connected and not self.busy:
            self.wake = True
        return DISCONNECTED_MESSAGE

    def take_wake(self) -> bool:
        woke = self.wake
        self.wake = False
        return woke
