"""The HoMedics Drift integration."""

from __future__ import annotations

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .coordinator import DriftConfigEntry, DriftCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: DriftConfigEntry) -> bool:
    """Connect to a Drift table and create its entities."""
    coordinator = DriftCoordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _release(_event: Event) -> None:
        _LOGGER.debug("Home Assistant is stopping; releasing Drift %s", coordinator.address)
        await coordinator.async_shutdown()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _release))
    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DriftConfigEntry) -> None:
    """Disconnect the table, then remove its entities."""
    await entry.runtime_data.async_shutdown()
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
