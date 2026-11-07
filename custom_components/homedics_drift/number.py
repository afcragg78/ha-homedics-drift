"""Speed control for a Drift table."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the speed slider."""
    async_add_entities([DriftSpeed(entry.runtime_data)])


class DriftSpeed(DriftEntity, NumberEntity):
    """Drawing speed. 0–100% maps onto the table's raw range 30–75."""

    _attr_translation_key = "speed"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the speed control."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-speed"

    @property
    def native_value(self) -> float:
        """Current speed as a percentage of the documented raw range."""
        return round(self._state.speed_percent, 1)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set the speed."""
        await self.coordinator.async_set_speed_percent(value)
