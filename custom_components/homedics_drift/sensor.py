"""Status, progress, and pattern sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DriftStatusSensor(coordinator),
            DriftProgressSensor(coordinator),
            DriftPatternSensor(coordinator),
        ]
    )


def _status_name(status: int) -> str:
    if status == 1:
        return "drawing"
    if status == 0:
        return "idle"
    return "unknown"


class DriftStatusSensor(DriftEntity, SensorEntity):
    """Drawing or idle, from the running-state status byte."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["drawing", "idle", "unknown"]
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-status"

    @property
    def native_value(self) -> str:
        """drawing, idle, or unknown."""
        return _status_name(self._state.status)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Fields the dedicated entities do not already show."""
        state = self._state
        return {
            "color_name": state.color_name,
            "playlist_id": state.playlist_id,
            "random": state.random_mode,
            "loop": state.loop_mode,
            "sleep": state.sleep,
            "breathing": state.breathing,
            "shifting": state.shifting,
            "shift_time": state.shift_time,
            "controller_version": state.controller_version,
            "driver_version": state.driver_version,
        }


class DriftProgressSensor(DriftEntity, SensorEntity):
    """Pattern progress. The wire value 0..10000 is shown as 0..100%."""

    _attr_translation_key = "progress"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-progress"

    @property
    def native_value(self) -> float:
        """Progress percentage."""
        return round(self._state.progress * 100, 2)


class DriftPatternSensor(DriftEntity, SensorEntity):
    """Pattern id currently reported by the table."""

    _attr_translation_key = "pattern"
    _attr_icon = "mdi:palette-outline"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-pattern"

    @property
    def native_value(self) -> int:
        """Pattern id. Zero is what the table reports while idle."""
        return self._state.pattern_id
