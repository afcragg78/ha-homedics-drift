"""Integration power switch for a Drift table."""

from __future__ import annotations

from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the power switch."""
    async_add_entities([DriftPowerSwitch(entry.runtime_data)])


class DriftPowerSwitch(DriftEntity, RestoreEntity, SwitchEntity):
    """Pause plus lamp off, remembered by Home Assistant.

    The table's ``powerOn`` flag is not a real off state, so this switch does
    not follow it. Play and pause cannot move it. Only this switch can.
    """

    _attr_translation_key = "power"
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-power"

    @property
    def is_on(self) -> bool:
        """The integration's own power state."""
        return self.coordinator.session_on

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Lamp memory restored with the switch after a restart."""
        return {
            "lamp_level": self.coordinator.lamp_brightness,
            "lamp_color": list(self.coordinator.lamp_color),
            "lamp_color_name": self.coordinator.lamp_color_name,
        }

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last switch position. Status packets do not supply it."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            self.coordinator.adopt_session(True)
            return
        self._restore_lamp(last.attributes)
        self.coordinator.adopt_session(last.state == STATE_ON)

    def _restore_lamp(self, attributes: dict[str, object]) -> None:
        level = attributes.get("lamp_level")
        if isinstance(level, (int, float)) and int(level) > 0:
            self.coordinator.lamp_brightness = int(level)
        color = attributes.get("lamp_color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            self.coordinator.lamp_color = (int(color[0]), int(color[1]), int(color[2]))
        name = attributes.get("lamp_color_name")
        if isinstance(name, str) and name:
            self.coordinator.lamp_color_name = name

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Restore the lamp and resume play."""
        await self.coordinator.async_set_power(True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Pause if the ball is moving, and turn the lamp off."""
        await self.coordinator.async_set_power(False)
