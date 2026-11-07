"""Soft power switch for a Drift table."""

from __future__ import annotations

from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the power switch."""
    async_add_entities([DriftPowerSwitch(entry.runtime_data)])


class DriftPowerSwitch(DriftEntity, SwitchEntity):
    """Table power via command 0x14/16. This does not switch a mains outlet."""

    _attr_translation_key = "power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-power"

    @property
    def is_on(self) -> bool | None:
        """The table's power flag, or the command still waiting for that flag.

        ``None`` stays unknown. It is not treated as off, so a missing byte
        cannot invert the next press.
        """
        return self._state.power_on

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the table on."""
        await self.coordinator.async_set_power(True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the table off."""
        await self.coordinator.async_set_power(False)
