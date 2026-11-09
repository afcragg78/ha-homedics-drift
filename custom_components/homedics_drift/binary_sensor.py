"""Diagnostic link sensor for a Drift table."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DriftConfigEntry, DriftCoordinator
from .entity import DriftEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DriftConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the connected sensor."""
    async_add_entities([DriftConnectedSensor(entry.runtime_data)])


class DriftConnectedSensor(DriftEntity, BinarySensorEntity):
    """On while the Bluetooth link is up. Stays available when the table is gone."""

    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Identify the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}-connected"

    @property
    def available(self) -> bool:
        """The other entities go unavailable. This one reports the link."""
        return True

    @property
    def is_on(self) -> bool:
        """True after the table accepts the GATT connection."""
        return self.coordinator.connected
