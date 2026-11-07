"""Constants for the HoMedics Drift integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "homedics_drift"

SERVICE_UUID: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
WRITE_UUID: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

MANUFACTURER: Final = "HoMedics"
MODEL: Final = "Drift ST-300/ST-400"

READY_TIMEOUT: Final = 30.0
BACKOFF_START: Final = 2.0
BACKOFF_MAX: Final = 60.0
