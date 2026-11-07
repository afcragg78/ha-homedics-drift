"""Dashboard text box for an AI drawing prompt."""

from __future__ import annotations

from typing import override

from homeassistant.components.text import TextEntity, TextMode
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
    """Create the prompt box."""
    async_add_entities([DriftPromptText(entry.runtime_data)])


class DriftPromptText(DriftEntity, RestoreEntity, TextEntity):
    """A prompt the Draw with AI button sends. Home Assistant stores no API key."""

    _attr_translation_key = "ai_prompt"
    _attr_icon = "mdi:form-textbox"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the text box."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-ai-prompt"

    @property
    def native_value(self) -> str:
        """The current prompt."""
        return self.coordinator.ai_prompt

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the last prompt."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable", None):
            self.coordinator.ai_prompt = last.state[:255]

    @override
    async def async_set_value(self, value: str) -> None:
        """Save the prompt. This does not call a model."""
        self.coordinator.ai_prompt = value.strip()[:255]
        self.async_write_ha_state()
