"""Home Assistant integration for HoMedics Drift sand tables.

Converted from Josh Lannin's Drifted project
(https://github.com/joshlannin/drifted) using Grok Bot. Drifted
reverse-engineered the Bluetooth protocol. The GitHub account that posted
this repository is not the author.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .coordinator import DriftConfigEntry, DriftCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register pattern services once for every table."""
    from .services import async_setup_services

    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DriftConfigEntry) -> bool:
    """Connect to a Drift table and create its entities."""
    coordinator = DriftCoordinator(hass, entry)
    await coordinator.async_load_library()
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
