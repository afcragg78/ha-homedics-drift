"""Playback controls for a Drift table."""

from __future__ import annotations

from typing import override

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the player."""
    async_add_entities([DriftPlayer(entry.runtime_data)])


class DriftPlayer(DriftEntity, MediaPlayerEntity):
    """Play, pause, and skip patterns.

    Play and pause are one toggle on the wire (0x14/3). Next and previous are
    0x14/4 and 0x14/5. Power is the separate switch; turning the player on
    only sends soft power when the table is off, then toggles playback if the
    ball is idle.
    """

    _attr_translation_key = "player"
    _attr_icon = "mdi:draw"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.TURN_ON
    )

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the player."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-player"

    @property
    def state(self) -> MediaPlayerState:
        """Off when the table is powered down, otherwise playing or paused."""
        if self._state.power_on is False:
            return MediaPlayerState.OFF
        if self._state.drawing:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.PAUSED

    @property
    def media_title(self) -> str:
        """Current pattern id."""
        return f"Pattern {self._state.pattern_id}"

    @property
    def media_playlist(self) -> str | None:
        """Playlist id from the running-state broadcast, when one is active."""
        return self._state.playlist_id or None

    @override
    async def async_turn_on(self) -> None:
        """Power the table on and start playback when it is idle."""
        if self._state.power_on is False:
            await self.coordinator.async_set_power(True)
        if not self._state.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_play(self) -> None:
        """Start drawing unless it is already drawing."""
        await self.async_turn_on()

    @override
    async def async_media_pause(self) -> None:
        """Pause when the ball is drawing. The toggle is not sent while idle."""
        if self._state.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_play_pause(self) -> None:
        """Send the table's play/pause toggle, powering on first if needed."""
        if self._state.power_on is False:
            await self.coordinator.async_set_power(True)
        await self.coordinator.async_toggle_playback()

    @override
    async def async_media_next_track(self) -> None:
        """Skip to the next pattern."""
        await self.coordinator.async_next()

    @override
    async def async_media_previous_track(self) -> None:
        """Skip to the previous pattern."""
        await self.coordinator.async_previous()
