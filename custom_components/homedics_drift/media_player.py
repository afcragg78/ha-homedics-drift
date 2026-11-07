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
from .protocol import playback_allowed, player_controls, shown_playback

_CONTROL_FEATURES = {
    "play": MediaPlayerEntityFeature.PLAY,
    "pause": MediaPlayerEntityFeature.PAUSE,
    "next": MediaPlayerEntityFeature.NEXT_TRACK,
    "previous": MediaPlayerEntityFeature.PREVIOUS_TRACK,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the player."""
    async_add_entities([DriftPlayer(entry.runtime_data)])


class DriftPlayer(DriftEntity, MediaPlayerEntity):
    """Play, pause, and skip. These buttons never move the power switch.

    While power is off the player reports off and advertises no play, pause,
    next, previous, or source controls, so the card has nothing to press.
    """

    _attr_translation_key = "player"
    _attr_icon = "mdi:draw"

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
    def supported_features(self) -> MediaPlayerEntityFeature:
        """No transport buttons while power is off. No player power button ever."""
        flags = MediaPlayerEntityFeature(0)
        for name in player_controls(self.coordinator.session_on):
            flags |= _CONTROL_FEATURES[name]
        return flags

    @property
    def state(self) -> MediaPlayerState | None:
        """Off for the whole time the power switch is off, without flicker."""
        if not self.coordinator.session_on or not self.coordinator.session_settled:
            return MediaPlayerState.OFF
        data = self.coordinator.data
        if data is None:
            return None
        activity = shown_playback(True, data.drawing, settled=True)
        if activity == "playing":
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

    def _awake(self) -> bool:
        return playback_allowed(self.coordinator.session_on)

    @override
    async def async_turn_on(self) -> None:
        """Does nothing. The Power switch is the only way to turn power on."""
        return

    @override
    async def async_media_play(self) -> None:
        """Start drawing. Ignored while power is off, and it does not turn power on."""
        if not self._awake():
            return
        data = self.coordinator.data
        if data is not None and not data.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_pause(self) -> None:
        """Pause when the ball is drawing. Does not change the power switch."""
        if not self._awake():
            return
        data = self.coordinator.data
        if data is not None and data.drawing:
            await self.coordinator.async_toggle_playback()

    @override
    async def async_media_play_pause(self) -> None:
        """Send the play/pause toggle. Ignored while power is off."""
        if not self._awake():
            return
        await self.coordinator.async_toggle_playback()

    @override
    async def async_media_next_track(self) -> None:
        """Skip to the next pattern. Ignored while power is off."""
        if not self._awake():
            return
        await self.coordinator.async_next()

    @override
    async def async_media_previous_track(self) -> None:
        """Skip to the previous pattern. Ignored while power is off."""
        if not self._awake():
            return
        await self.coordinator.async_previous()
