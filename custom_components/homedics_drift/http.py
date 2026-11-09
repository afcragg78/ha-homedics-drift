"""A small authenticated read of a pattern path this machine already stored.

The table is not queried. The dashboard asks once when the pattern id changes,
then moves the ball from the progress value Home Assistant already pushes.
"""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


def coordinator_for_device(hass: HomeAssistant, device_id: str):
    """The Drift coordinator that owns this device, if it is one of ours."""
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return getattr(entry, "runtime_data", None)
    return None


class DriftPathView(HomeAssistantView):
    """Polar points for the pattern on the table, when this machine has them."""

    url = "/api/homedics_drift/path/{device_id}"
    name = "api:homedics_drift:path"
    requires_auth = True

    async def get(self, request: web.Request, device_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = coordinator_for_device(hass, device_id)
        pattern_id = 0
        points = None
        if coordinator is not None and coordinator.data is not None:
            pattern_id = int(coordinator.data.pattern_id or 0)
            if pattern_id > 0:
                points = coordinator.known_path(pattern_id)
        return self.json({"pattern_id": pattern_id, "points": points})
