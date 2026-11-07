"""Playlist select fed by the table's own catalogue."""

from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity
from .gallery import gallery_names, gallery_picture


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the playlist and pattern selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DriftPlaylistSelect(coordinator),
            DriftPatternSelect(coordinator),
            DriftInboxSelect(coordinator),
            DriftGallerySelect(coordinator),
        ]
    )


class DriftPlaylistSelect(DriftEntity, SelectEntity):
    """Every playlist the table listed during this connection.

    The options are rebuilt from command 0x30 each time the handshake runs.
    Nothing is hardcoded. A playlist with no name is shown as ``Playlist N``.
    Choosing one sends draw-from-playlist (0x14/2) with that playlist's id and
    its first pattern id, or pattern 0 when the table did not include ids.
    """

    _attr_translation_key = "playlist"
    _attr_icon = "mdi:playlist-play"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-playlist"

    @property
    def options(self) -> list[str]:
        """Labels from the live catalogue."""
        return [label for label, _playlist in self.coordinator.catalogue.options()]

    @property
    def current_option(self) -> str | None:
        """The playlist id in the latest running state, when it is in the list."""
        return self.coordinator.catalogue.label_for(self._state.playlist_id)

    @override
    async def async_select_option(self, option: str) -> None:
        """Switch the table to this playlist."""
        await self.coordinator.async_select_playlist(option)


class DriftPatternSelect(DriftEntity, SelectEntity):
    """Every pattern id the table listed.

    Uploaded patterns and renamed stock ids use the name saved on this
    Home Assistant machine. Choosing one plays that id. Power off blocks it.
    """

    _attr_translation_key = "pattern"
    _attr_icon = "mdi:palette-outline"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-pattern-select"

    @property
    def options(self) -> list[str]:
        """Stored pattern labels, in id order."""
        return [label for label, _pattern_id in self.coordinator.pattern_choices()]

    @property
    def current_option(self) -> str | None:
        """The pattern in the latest running state, when the table has stored it."""
        current = self._state.pattern_id
        for label, pattern_id in self.coordinator.pattern_choices():
            if pattern_id == current:
                return label
        return None

    @override
    async def async_select_option(self, option: str) -> None:
        """Play this stored pattern."""
        await self.coordinator.async_select_pattern(option)


class DriftInboxSelect(DriftEntity, SelectEntity):
    """``.thr`` files in the pattern folder that have not been uploaded.

    Choosing one only marks it. The upload button sends it.
    """

    _attr_translation_key = "inbox"
    _attr_icon = "mdi:file-import"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-inbox"

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.inbox)

    @property
    def current_option(self) -> str | None:
        if self.coordinator.inbox_choice in self.coordinator.inbox:
            return self.coordinator.inbox_choice
        return None

    @override
    async def async_select_option(self, option: str) -> None:
        """Remember the file. This does not upload it."""
        if option not in self.coordinator.inbox:
            return
        self.coordinator.inbox_choice = option
        self.async_write_ha_state()


class DriftGallerySelect(DriftEntity, SelectEntity):
    """Shipped designs. Choosing one shows its picture and does not upload."""

    _attr_translation_key = "gallery"
    _attr_icon = "mdi:image-filter-vintage"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the select."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-gallery"

    @property
    def options(self) -> list[str]:
        return gallery_names()

    @property
    def current_option(self) -> str | None:
        if self.coordinator.gallery_choice in self.options:
            return self.coordinator.gallery_choice
        return self.options[0]

    @property
    def entity_picture(self) -> str | None:
        """Preview of the design that is currently chosen."""
        return gallery_picture(self.current_option or "")

    @override
    async def async_select_option(self, option: str) -> None:
        """Remember the design. The send button uploads it."""
        if option not in gallery_names():
            return
        from datetime import datetime, timezone

        self.coordinator.gallery_choice = option
        self.coordinator.gallery_preview_at = datetime.now(timezone.utc)
        self.coordinator.async_update_listeners()
