"""Home Assistant integration for HoMedics Drift sand tables.

Converted from Josh Lannin's Drifted project
(https://github.com/joshlannin/drifted) using Grok Bot. Drifted
reverse-engineered the Bluetooth protocol. The GitHub account that posted
this repository is not the author.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import DriftConfigEntry, DriftCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register pattern services and the dashboard card once."""
    from .http import DriftLibraryView, DriftPathView
    from .services import async_setup_services

    await async_setup_services(hass)
    if not hass.data.get(f"{DOMAIN}_card"):
        await _async_register_card(hass)
        hass.http.register_view(DriftPathView())
        hass.http.register_view(DriftLibraryView())
        hass.data[f"{DOMAIN}_card"] = True
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and ask the frontend to load it. No HACS frontend step."""
    from homeassistant.components.frontend import add_extra_js_url

    www = Path(__file__).parent / "www"
    root = f"/{DOMAIN}"
    # Query string so a browser that cached the previous card fetches this one.
    url = f"{root}/drift-table-card.js?v=3"
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths([StaticPathConfig(root, str(www), True)])
    except Exception:
        hass.http.register_static_path(root, str(www), True)
    add_extra_js_url(hass, url)


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
