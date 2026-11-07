"""Preview of the pattern that is on now, when this machine has a picture."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the now-playing preview."""
    async_add_entities([DriftPreviewImage(entry.runtime_data)])


class DriftPreviewImage(DriftEntity, ImageEntity):
    """PNG of the current pattern, if it was uploaded or saved here."""

    _attr_translation_key = "preview"
    _attr_content_type = "image/png"
    _attr_icon = "mdi:image"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the image and the access token Home Assistant expects."""
        super().__init__(coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{coordinator.address}-preview"

    @property
    def image_last_updated(self) -> datetime | None:
        """Changes when the current pattern or its picture changes."""
        return self.coordinator.preview_at

    async def async_image(self) -> bytes | None:
        """The saved PNG, or nothing when this pattern has no preview."""
        return await self.hass.async_add_executor_job(self.coordinator.preview_bytes)
