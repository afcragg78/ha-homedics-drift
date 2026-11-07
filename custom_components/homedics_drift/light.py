"""Lamp entity for a Drift table."""

from __future__ import annotations

from typing import Any, override

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


def _table_to_ha(level: int) -> int:
    if level <= 0:
        return 0
    return max(1, min(255, round(level * 255 / 100)))


def _ha_to_table(level: int) -> int:
    if level <= 0:
        return 0
    return max(1, min(100, round(level * 100 / 255)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the lamp."""
    async_add_entities([DriftLight(entry.runtime_data)])


class DriftLight(DriftEntity, LightEntity):
    """RGB lamp. On/off follows brightness, not the table's motor power."""

    _attr_translation_key = "lamp"
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the lamp."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-light"

    @property
    def is_on(self) -> bool:
        """True when the reported brightness is above zero."""
        return self._state.brightness > 0

    @property
    def brightness(self) -> int | None:
        """Home Assistant brightness, 1..255, from the table's 0..100 scale."""
        level = _table_to_ha(self._state.brightness)
        return level or None

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Colour from the running-state broadcast."""
        return self._state.color

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set colour, brightness, or both. Colour is stored as palette Temp."""
        current = self._state.brightness or self.coordinator.lamp_brightness or 100
        if ATTR_BRIGHTNESS in kwargs:
            level = _ha_to_table(kwargs[ATTR_BRIGHTNESS])
        else:
            level = current
        if level <= 0:
            level = self.coordinator.lamp_brightness or 100
        if ATTR_RGB_COLOR in kwargs:
            await self.coordinator.async_set_color(kwargs[ATTR_RGB_COLOR], level)
            return
        await self.coordinator.async_set_brightness(level)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Dim the lamp to zero. Table power is left to the power switch."""
        await self.coordinator.async_set_brightness(0)
