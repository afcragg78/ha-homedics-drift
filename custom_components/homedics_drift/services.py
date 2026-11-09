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
SERVICE_AI_DRAW = "ai_draw"
SERVICE_GENERATE = "generate_pattern"
SERVICE_GALLERY = "add_gallery_design"
SERVICE_IMPORT = "import_pattern_url"
SERVICE_FAVORITE = "set_favorite"

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
_AI_SCHEMA = vol.Schema(
    {
        vol.Required("prompt"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("play", default=False): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)
_IMPORT_SCHEMA = vol.Schema(
    {vol.Required("url"): cv.string},
    extra=vol.ALLOW_EXTRA,
)
_FAVORITE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("favorite", default=True): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)
_GALLERY_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("play", default=False): cv.boolean,
    },
    extra=vol.ALLOW_EXTRA,
)
_GENERATE_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["spiral", "rose", "star", "wave", "spirograph"]),
        vol.Optional("name"): cv.string,
        vol.Optional("play", default=False): cv.boolean,
        vol.Optional("turns"): vol.Coerce(float),
        vol.Optional("outward"): cv.boolean,
        vol.Optional("petals"): vol.Coerce(float),
        vol.Optional("points"): vol.Coerce(float),
        vol.Optional("waves"): vol.Coerce(float),
        vol.Optional("loops"): vol.Coerce(float),
        vol.Optional("outer"): vol.Coerce(float),
        vol.Optional("inner"): vol.Coerce(float),
        vol.Optional("pen"): vol.Coerce(float),
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

    async def _ai_draw(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_ai_draw(
            call.data["prompt"],
            name=call.data.get("name"),
            play=bool(call.data.get("play")),
        )

    async def _generate(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        params = {
            key: call.data[key]
            for key in ("turns", "outward", "petals", "points", "waves", "loops", "outer", "inner", "pen")
            if key in call.data
        }
        await coordinator.async_generate_pattern(
            call.data["type"],
            params,
            name=call.data.get("name"),
            play=bool(call.data.get("play")),
        )

    hass.services.async_register(DOMAIN, SERVICE_UPLOAD, _upload, schema=_UPLOAD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, _delete, schema=_DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RENAME, _rename, schema=_RENAME_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_AI_DRAW, _ai_draw, schema=_AI_SCHEMA)
    async def _gallery(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_add_gallery_design(
            call.data["name"],
            play=bool(call.data.get("play")),
        )

    hass.services.async_register(DOMAIN, SERVICE_GENERATE, _generate, schema=_GENERATE_SCHEMA)
    async def _import(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_import_pattern_url(call.data["url"])

    async def _favorite(call: ServiceCall) -> None:
        coordinator = await _coordinator(hass, call)
        await coordinator.async_set_favorite(call.data["name"], bool(call.data.get("favorite", True)))

    hass.services.async_register(DOMAIN, SERVICE_GALLERY, _gallery, schema=_GALLERY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_IMPORT, _import, schema=_IMPORT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FAVORITE, _favorite, schema=_FAVORITE_SCHEMA)


async def _coordinator(hass: HomeAssistant, call: ServiceCall) -> DriftCoordinator:
    """The one table named by the service call."""
    # Home Assistant 2026 takes the service call only. Passing hass first makes
    # it read hass.hass and the Draw button fails.
    extracted = async_extract_config_entry_ids(call)
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
