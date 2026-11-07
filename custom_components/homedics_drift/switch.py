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
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DriftPowerSwitch(coordinator),
            DriftCleanBeforeSwitch(coordinator),
            DriftFavoriteSwitch(coordinator),
        ]
    )


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


class DriftCleanBeforeSwitch(DriftEntity, RestoreEntity, SwitchEntity):
    """When on, choosing a pattern wipes the sand first. Play and pause do not."""

    _attr_translation_key = "clean_before"
    _attr_icon = "mdi:broom"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-clean-before"

    @property
    def is_on(self) -> bool:
        """Local option. The table is not asked."""
        return self.coordinator.library.clean_before

    @property
    def available(self) -> bool:
        """Shown whenever the table is connected, including while Power is off."""
        return super().available

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last choice if the library has not already loaded one."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None or self.coordinator.library.clean_before:
            return
        if last.state == STATE_ON:
            await self.coordinator.async_set_clean_before(True)

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Wipe before the next pattern that is chosen. Does not start a wipe now."""
        await self.coordinator.async_set_clean_before(True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Choose patterns without wiping first."""
        await self.coordinator.async_set_clean_before(False)


class DriftFavoriteSwitch(DriftEntity, SwitchEntity):
    """Mark the gallery design that is on screen. Choosing it later does not need a prompt."""

    _attr_translation_key = "favorite"
    _attr_icon = "mdi:heart"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-favorite"

    @property
    def is_on(self) -> bool:
        """Whether the design currently chosen in the gallery is a favorite."""
        return self.coordinator.gallery_choice in self.coordinator.library.favorites

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Save the chosen gallery design as a favorite."""
        await self.coordinator.async_set_favorite(self.coordinator.gallery_choice, True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Remove the chosen gallery design from favorites."""
        await self.coordinator.async_set_favorite(self.coordinator.gallery_choice, False)
