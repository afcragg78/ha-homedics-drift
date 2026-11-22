"""Constants for the HoMedics Drift integration."""

from __future__ import annotations

import asyncio

from typing import Any, Final

DOMAIN: Final = "homedics_drift"

SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

MANUFACTURER: Final = "HoMedics"
MODEL: Final = "Drift ST-300/ST-400"

READY_TIMEOUT: Final = 30.0
# Wait this long for a connected link and a finished handshake before an upload.
UPLOAD_LINK_WAIT: Final = 30.0
# UPLOAD_STORED wait: 15s, plus 0.1s per page, never more than 60s.
UPLOAD_STORE_TIMEOUT: Final = 15.0
UPLOAD_STORE_TIMEOUT_PER_PAGE: Final = 0.1
UPLOAD_STORE_TIMEOUT_MAX: Final = 60.0
# After pausing a running playlist, wait briefly for the ball to stop.
UPLOAD_PAUSE_SETTLE: Final = 1.0
UPLOAD_PAUSE_WAIT: Final = 5.0
# After a large upload, pause before Clean or Play so the table can settle.
UPLOAD_SETTLE_PAGES: Final = 150
UPLOAD_SETTLE_SECONDS: Final = 4.0
# Weather drawings stay at or under this many 40-point pages.
WEATHER_MAX_PAGES: Final = 280
WEATHER_MAX_POINTS: Final = WEATHER_MAX_PAGES * 40
BACKOFF_START: Final = 2.0
BACKOFF_MAX: Final = 60.0
# Rapid power taps become one absolute write of the last requested value.
POWER_DEBOUNCE: Final = 0.2

CONF_PREFERRED_ADAPTER: Final = "preferred_bluetooth_adapter"
CONF_AI_TASK_ENTITY: Final = "ai_task_entity"
CONF_CONVERSATION_AGENT: Final = "conversation_agent"
CONF_CLEAN_BEFORE_AI: Final = "clean_before_ai"
CONF_WEATHER_ENTITY: Final = "weather_entity"
CONF_WEATHER_UNIT: Final = "weather_unit"
CONF_WEATHER_ROTATION: Final = "weather_rotation"
CONF_WEATHER_AFTER_PATTERN: Final = "weather_after_pattern"
CONF_WEATHER_COOLDOWN_MIN: Final = "weather_cooldown_min"
CONF_WEATHER_WIND: Final = "weather_wind_threshold"
CONF_WEATHER_HOT: Final = "weather_hot_threshold"
CONF_WEATHER_COLD: Final = "weather_cold_threshold"
CONF_WEATHER_HEAVY: Final = "weather_heavy_probability"
CONF_WEATHER_ALERT: Final = "weather_alert_entity"
CONF_PHOTO_CAMERA: Final = "photo_feedback_camera"


def should_pause_for_upload(*, drawing: bool, progress: float | None) -> bool:
    """True when a running pattern or playlist should be paused before upload.

    ``play_pause`` is a toggle, so this is false when the ball is already
    still, including a Stop-after pause that leaves drawing true at ~99%.
    """
    if not drawing:
        return False
    if progress is None:
        return True
    return progress < 0.99



class UploadPauseAborted(Exception):
    """Pause-for-upload stopped because power was lost or the link dropped."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def wait_for_pause_to_take(
    *,
    is_moving: Any,
    is_shut_down: Any,
    is_powered: Any,
    settle: float = UPLOAD_PAUSE_SETTLE,
    timeout: float = UPLOAD_PAUSE_WAIT,
    sleep: Any = asyncio.sleep,
    clock: Any | None = None,
) -> None:
    """Wait briefly after a pause command until the ball is still, then return."""
    now = clock or (lambda: asyncio.get_running_loop().time())
    started = now()
    deadline = started + timeout
    while now() < deadline:
        if is_shut_down():
            raise UploadPauseAborted("disconnected")
        if not is_powered():
            raise UploadPauseAborted("power_off")
        if not is_moving() and now() - started >= settle:
            return
        await sleep(0.2)


def store_confirm_timeout(page_count: int) -> float:
    """Seconds to wait for the table to confirm a stored pattern.

    Larger drawings get more time after the last page is sent, up to
    ``UPLOAD_STORE_TIMEOUT_MAX``.
    """
    pages = max(0, int(page_count))
    return min(
        UPLOAD_STORE_TIMEOUT_MAX,
        UPLOAD_STORE_TIMEOUT + UPLOAD_STORE_TIMEOUT_PER_PAGE * pages,
    )
