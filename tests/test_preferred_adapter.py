"""Preferred Bluetooth adapter picking does not fall back to another scanner."""

from __future__ import annotations

from custom_components.homedics_drift.preferred_adapter import (
    PREFERRED_ADAPTER_AUTO,
    ble_device_for_preferred_adapter,
    preferred_adapter_label,
    preferred_adapter_value,
)


def test_unset_or_blank_is_automatic() -> None:
    assert preferred_adapter_value(None) == PREFERRED_ADAPTER_AUTO
    assert preferred_adapter_value("") == PREFERRED_ADAPTER_AUTO
    assert preferred_adapter_value("  ") == PREFERRED_ADAPTER_AUTO
    assert preferred_adapter_value("Automatic") == PREFERRED_ADAPTER_AUTO
    assert preferred_adapter_value("automatic") == PREFERRED_ADAPTER_AUTO
    assert preferred_adapter_value("00:E0:42:CD:E8:03") == "00:E0:42:CD:E8:03"
    assert preferred_adapter_value("  00:E0:42:CD:E8:03  ") == "00:E0:42:CD:E8:03"


def test_picker_matches_source_case_insensitively() -> None:
    dongle = object()
    proxy = object()
    paths = [
        ("D8:BC:38:4C:AA:E4", proxy),
        ("00:E0:42:CD:E8:03", dongle),
    ]
    assert (
        ble_device_for_preferred_adapter("00:e0:42:cd:e8:03", paths) is dongle
    )
    assert ble_device_for_preferred_adapter("00:E0:42:CD:E8:03", paths) is dongle


def test_picker_returns_none_when_adapter_does_not_see_the_device() -> None:
    proxy = object()
    assert (
        ble_device_for_preferred_adapter(
            "00:E0:42:CD:E8:03",
            [("D8:BC:38:4C:AA:E4", proxy)],
        )
        is None
    )
    assert ble_device_for_preferred_adapter("00:E0:42:CD:E8:03", []) is None
    # Automatic is not a source match; the coordinator uses HA's default path.
    assert ble_device_for_preferred_adapter("automatic", [("00:E0:42:CD:E8:03", proxy)]) is None


def test_label_includes_rssi_only_when_known() -> None:
    assert (
        preferred_adapter_label("Realtek Bluetooth 5.1 Radio", "00:E0:42:CD:E8:03")
        == "Realtek Bluetooth 5.1 Radio (00:E0:42:CD:E8:03)"
    )
    assert (
        preferred_adapter_label(
            "Realtek Bluetooth 5.1 Radio", "00:E0:42:CD:E8:03", -42
        )
        == "Realtek Bluetooth 5.1 Radio (00:E0:42:CD:E8:03) (-42 dBm)"
    )
    assert preferred_adapter_label("", "00:E0:42:CD:E8:03") == "00:E0:42:CD:E8:03 (00:E0:42:CD:E8:03)"
