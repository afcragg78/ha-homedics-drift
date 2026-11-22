"""Pick a BLE path when a preferred Bluetooth adapter is set."""

from __future__ import annotations

from typing import TypeVar

PREFERRED_ADAPTER_AUTO = "automatic"

T = TypeVar("T")


def preferred_adapter_value(value: object) -> str:
    """The stored scanner source, or Automatic when the option is unset."""
    if not isinstance(value, str):
        return PREFERRED_ADAPTER_AUTO
    text = value.strip()
    if not text or text.lower() == PREFERRED_ADAPTER_AUTO:
        return PREFERRED_ADAPTER_AUTO
    return text


def ble_device_for_preferred_adapter(
    preferred: str, paths: list[tuple[str, T]]
) -> T | None:
    """The device whose scanner source matches ``preferred``, or None."""
    want = preferred_adapter_value(preferred)
    if want == PREFERRED_ADAPTER_AUTO:
        return None
    for source, device in paths:
        if isinstance(source, str) and source.strip().lower() == want.lower():
            return device
    return None


def preferred_adapter_label(
    name: str, source: str, rssi: int | float | None = None
) -> str:
    """Dropdown line: scanner name, source address, and RSSI when known."""
    source = source.strip()
    title = (name or "").strip() or source
    if rssi is None:
        return f"{title} ({source})"
    try:
        measured = int(rssi)
    except (TypeError, ValueError):
        return f"{title} ({source})"
    return f"{title} ({source}) ({measured} dBm)"
