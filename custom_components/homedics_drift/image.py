"""Preview of the pattern that is on now, when this machine has a picture."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity
from .gallery import gallery_names, gallery_polar
from .preview import render_preview


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the now-playing preview."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DriftPreviewImage(coordinator),
            DriftGalleryImage(coordinator),
            *[DriftGalleryTile(coordinator, name) for name in gallery_names()],
        ]
    )


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


class DriftGalleryImage(DriftEntity, ImageEntity):
    """Larger sand picture of the gallery design that is selected."""

    _attr_translation_key = "gallery_preview"
    _attr_content_type = "image/png"
    _attr_icon = "mdi:image-filter-vintage"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the image."""
        super().__init__(coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_unique_id = f"{coordinator.address}-gallery-preview"

    @property
    def image_last_updated(self) -> datetime | None:
        """Changes when another gallery design is chosen."""
        return self.coordinator.gallery_preview_at

    async def async_image(self) -> bytes | None:
        """Render the chosen design. Nothing is sent to the table."""
        name = self.coordinator.gallery_choice

        def _draw() -> bytes:
            return render_preview(gallery_polar(name), size=256)

        return await self.hass.async_add_executor_job(_draw)


class DriftGalleryTile(DriftEntity, ImageEntity):
    """One gallery picture, so a dashboard can show a grid of them."""

    _attr_has_entity_name = True
    _attr_translation_key = "gallery_tile"
    _attr_content_type = "image/png"
    _attr_icon = "mdi:image-filter-vintage"

    def __init__(self, coordinator: DriftCoordinator, design: str) -> None:
        """Identify this design's picture."""
        super().__init__(coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._design = design
        self._attr_name = design
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in design).strip("-")
        self._attr_unique_id = f"{coordinator.address}-gallery-tile-{slug}"

    async def async_image(self) -> bytes | None:
        """The sand picture for this one design."""
        design = self._design

        def _draw() -> bytes:
            return render_preview(gallery_polar(design), size=256)

        return await self.hass.async_add_executor_job(_draw)
