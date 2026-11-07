"""Status, progress, and pattern sensors."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity
from .protocol import playlist_pattern_index


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            DriftStatusSensor(coordinator),
            DriftProgressSensor(coordinator),
            DriftPatternSensor(coordinator),
            DriftNowPlayingSensor(coordinator),
            DriftSlotSensor(coordinator),
            DriftAiJobSensor(coordinator),
        ]
    )


def _status_name(status: int) -> str:
    if status == 1:
        return "drawing"
    if status == 0:
        return "idle"
    return "unknown"


class DriftStatusSensor(DriftEntity, SensorEntity):
    """Drawing or idle, from the running-state status byte."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["drawing", "idle", "unknown"]
    _attr_icon = "mdi:information-outline"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-status"

    @property
    def native_value(self) -> str:
        """drawing, idle, or unknown."""
        return _status_name(self._state.status)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Fields the dedicated entities do not already show."""
        state = self._state
        return {
            "color_name": state.color_name,
            "playlist_id": state.playlist_id,
            "random": state.random_mode,
            "loop": state.loop_mode,
            "sleep": state.sleep,
            "breathing": state.breathing,
            "shifting": state.shifting,
            "shift_time": state.shift_time,
            "controller_version": state.controller_version,
            "driver_version": state.driver_version,
        }


class DriftProgressSensor(DriftEntity, SensorEntity):
    """Pattern progress. The wire value 0..10000 is shown as 0..100%."""

    _attr_translation_key = "progress"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-progress"

    @property
    def native_value(self) -> float:
        """Progress percentage."""
        return round(self._state.progress * 100, 2)


class DriftPatternSensor(DriftEntity, SensorEntity):
    """Pattern id currently reported by the table."""

    _attr_translation_key = "pattern"
    _attr_icon = "mdi:palette-outline"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-pattern"

    @property
    def native_value(self) -> int:
        """Pattern id. Zero is what the table reports while idle."""
        return self._state.pattern_id


class DriftNowPlayingSensor(DriftEntity, SensorEntity):
    """The pattern the table is on, plus the list of everything it has stored.

    The name is ``Pattern N`` because the table's own list is ids, not titles.
    Playlist, the 1-based position in that playlist, and progress come from the
    running-state broadcast the table already sends. The stored-name list is
    the ``0x33`` dump from the handshake, not a separate read.
    """

    _attr_translation_key = "now_playing"
    _attr_icon = "mdi:draw"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-now-playing"

    @property
    def native_value(self) -> str:
        """Current pattern label, or Idle when the table reports pattern 0."""
        label = self.coordinator.display_name(self._state.pattern_id)
        return label if label is not None else "Idle"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Playlist, index, progress, and every stored pattern label."""
        state = self._state
        playlist = self.coordinator.catalogue.playlist_for(state.playlist_id)
        index = None
        if playlist is not None:
            index = playlist_pattern_index(playlist.pattern_ids, state.pattern_id)
        return {
            "playlist": self.coordinator.catalogue.label_for(state.playlist_id),
            "pattern_id": state.pattern_id,
            "pattern_index": index,
            "progress": round(state.progress * 100, 2),
            "path_known": self.coordinator.has_known_path(state.pattern_id),
            "stored_patterns": [label for label, _pattern_id in self.coordinator.pattern_choices()],
        }


class DriftSlotSensor(DriftEntity, SensorEntity):
    """How many patterns the table has stored, and how many new ones are allowed."""

    _attr_translation_key = "slots"
    _attr_icon = "mdi:database"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-slots"

    @property
    def native_value(self) -> int:
        """Patterns the table has listed."""
        used, _free = self.coordinator.slot_counts()
        return used

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Free slots under the cap, and files waiting in the folder."""
        used, free = self.coordinator.slot_counts()
        return {"used": used, "free": free, "cap": 700, "inbox": list(self.coordinator.inbox)}


class DriftAiJobSensor(DriftEntity, SensorEntity):
    """Last prompt drawing: idle, running, stored, or error."""

    _attr_translation_key = "ai_job"
    _attr_icon = "mdi:robot"

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-ai-job"

    @property
    def native_value(self) -> str:
        """idle, running, stored, or error."""
        return self.coordinator.ai_status

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """The last error, name, and whether an assistant is available."""
        return {
            "error": self.coordinator.ai_error,
            "detail": self.coordinator.ai_detail,
            "name": self.coordinator.ai_name,
            "pattern_id": self.coordinator.ai_pattern_id,
            "prompt": self.coordinator.ai_prompt[:255],
            "ai_available": self.coordinator.ai_available(),
            "progress": self.coordinator.ai_progress,
        }
