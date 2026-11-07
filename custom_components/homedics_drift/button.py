"""Buttons that refresh the pattern folder or upload the chosen file."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the folder buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [DriftRefreshButton(coordinator), DriftUploadButton(coordinator)]
    )


class DriftRefreshButton(DriftEntity, ButtonEntity):
    """Look again for .thr files. This does not upload anything."""

    _attr_translation_key = "refresh_patterns"
    _attr_icon = "mdi:folder-refresh"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-refresh-patterns"

    @override
    async def async_press(self) -> None:
        """Rescan /config/drift_patterns."""
        await self.coordinator.async_refresh_inbox()


class DriftUploadButton(DriftEntity, ButtonEntity):
    """Upload the .thr file chosen in the folder select."""

    _attr_translation_key = "upload_folder_pattern"
    _attr_icon = "mdi:upload"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-upload-folder-pattern"

    @override
    async def async_press(self) -> None:
        """Send the chosen file. Dropping a file in the folder does not do this."""
        await self.coordinator.async_upload_inbox()
