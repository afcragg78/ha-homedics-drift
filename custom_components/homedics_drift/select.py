"""Playlist select fed by the table's own catalogue."""

from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the playlist and pattern selects."""
    coordinator = entry.runtime_data
    async_add_entities(
        [DriftPlaylistSelect(coordinator), DriftPatternSelect(coordinator)]
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
    """Every pattern id the table listed, shown as ``Pattern N``.

    Choosing one sends draw-pattern (``0x14/1``). The list is the handshake
    dump (``0x33``), refreshed when the table sends it again. Soft sleep
    blocks the command so picking a pattern does not wake the table.
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
        return [label for label, _pattern_id in self.coordinator.patterns.options()]

    @property
    def current_option(self) -> str | None:
        """The pattern in the latest running state, when the table has stored it."""
        current = self._state.pattern_id
        for label, pattern_id in self.coordinator.patterns.options():
            if pattern_id == current:
                return label
        return None

    @override
    async def async_select_option(self, option: str) -> None:
        """Play this stored pattern."""
        await self.coordinator.async_select_pattern(option)
