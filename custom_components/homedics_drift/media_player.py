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
from .protocol import playback_allowed


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
    def available(self) -> bool:
        """Available whenever the table is connected, same as the other entities."""
        return super().available

    @property
    def entity_picture(self) -> None:
        """No artwork. The base player reads this even while unavailable."""
        return None

    @property
    def state(self) -> MediaPlayerState | None:
        """Playing or paused from the drawing status. Off while soft power is off."""
        data = self.coordinator.data
        if data is None:
            return None
        if data.power_on is False:
            return MediaPlayerState.OFF
        if data.playback == "playing":
            return MediaPlayerState.PLAYING
        return MediaPlayerState.PAUSED

    @property
    def media_title(self) -> str | None:
        """Current pattern as ``Pattern N``, once a status packet has arrived."""
        data = self.coordinator.data
        if data is None:
            return None
        return self.coordinator.patterns.label_for(data.pattern_id)

    @property
    def media_playlist(self) -> str | None:
        """Playlist name from the catalogue, when the running state names one."""
        data = self.coordinator.data
        if data is None or not data.playlist_id:
            return None
        return self.coordinator.catalogue.label_for(data.playlist_id)

    def _asleep(self) -> bool:
        data = self.coordinator.data
        return data is not None and not playback_allowed(data.power_on)

    @override
    async def async_turn_on(self) -> None:
        """Wake soft sleep. The power switch follows. Playback stays stopped."""
        await self.coordinator.async_set_power(True)

    @override
    async def async_media_play(self) -> None:
        """Start drawing unless the table is asleep or already drawing."""
        if self._asleep():
            return
        data = self.coordinator.data
        if data is not None and not data.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_pause(self) -> None:
        """Pause when the ball is drawing. Ignored while soft power is off."""
        if self._asleep():
            return
        data = self.coordinator.data
        if data is not None and data.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_play_pause(self) -> None:
        """Send the play/pause toggle. Ignored while soft power is off."""
        if self._asleep():
            return
        await self.coordinator.async_toggle_playback()

    @override
    async def async_media_next_track(self) -> None:
        """Skip to the next pattern. Ignored while soft power is off."""
        if self._asleep():
            return
        await self.coordinator.async_next()

    @override
    async def async_media_previous_track(self) -> None:
        """Skip to the previous pattern. Ignored while soft power is off."""
        if self._asleep():
            return
        await self.coordinator.async_previous()
