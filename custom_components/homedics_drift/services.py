"""Services for uploading, deleting, and renaming patterns."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids
import voluptuous as vol

from .const import DOMAIN
from .coordinator import DriftCoordinator

SERVICE_UPLOAD = "upload_pattern"
SERVICE_DELETE = "delete_pattern"
SERVICE_RENAME = "rename_pattern"

_UPLOAD_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("path"): cv.string,
        vol.Optional("thr"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)
_DELETE_SCHEMA = vol.Schema(
    {
        vol.Optional("pattern_id"): cv.positive_int,
        vol.Optional("name"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)
_RENAME_SCHEMA = vol.Schema(
    {
        vol.Required("pattern_id"): cv.positive_int,
        vol.Required("name"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the pattern services if they are not already registered."""
    if hass.services.has_service(DOMAIN, SERVICE_UPLOAD):
        return

    async def _upload(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_upload_pattern(
            name=call.data["name"],
            path=call.data.get("path"),
            thr=call.data.get("thr"),
        )

    async def _delete(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_delete_pattern(
            pattern_id=call.data.get("pattern_id"),
            name=call.data.get("name"),
        )

    async def _rename(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_rename_pattern(call.data["pattern_id"], call.data["name"])

    hass.services.async_register(DOMAIN, SERVICE_UPLOAD, _upload, schema=_UPLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, _delete, schema=_DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RENAME, _rename, schema=_RENAME_SCHEMA)


async def _coordinator(hass: HomeAssistant, call: ServiceCall) -> DriftCoordinator:
    """The one table named by the service call."""
    extracted = async_extract_config_entry_ids(hass, call)
    if hasattr(extracted, "__await__"):
        extracted = await extracted
    found: list[DriftCoordinator] = []
    for entry_id in extracted:
        entry = hass.config_entries.async_get_entry(entry_id)
        runtime = getattr(entry, "runtime_data", None)
        if entry is not None and entry.domain == DOMAIN and isinstance(runtime, DriftCoordinator):
            found.append(runtime)
    if not found:
        for entry in hass.config_entries.async_entries(DOMAIN):
            runtime = getattr(entry, "runtime_data", None)
            if isinstance(runtime, DriftCoordinator):
                found.append(runtime)
    if len(found) != 1:
        raise ServiceValidationError("Choose one Drift table")
    return found[0]
