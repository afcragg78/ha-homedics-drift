"""Service calls go through the same handler the Draw button uses."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest
import voluptuous as vol


class _ServiceCall:
    def __init__(self, hass: object, domain: str, service: str, data: dict) -> None:
        self.hass = hass
        self.domain = domain
        self.service = service
        self.data = data


class _Services:
    def __init__(self, hass: object) -> None:
        self._hass = hass
        self._handlers: dict[tuple[str, str], tuple] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._handlers

    def async_register(self, domain: str, service: str, handler, schema=None, **_kwargs) -> None:
        self._handlers[(domain, service)] = (handler, schema)

    async def async_call(self, domain: str, service: str, data: dict) -> None:
        handler, schema = self._handlers[(domain, service)]
        if schema is not None:
            data = schema(dict(data))
        await handler(_ServiceCall(self._hass, domain, service, data))


class _Entry:
    def __init__(self, entry_id: str, runtime: object) -> None:
        self.entry_id = entry_id
        self.domain = "homedics_drift"
        self.runtime_data = runtime


class _ConfigEntries:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def add(self, entry_id: str, runtime: object) -> None:
        self._entries[entry_id] = _Entry(entry_id, runtime)

    def async_get_entry(self, entry_id: str):
        return self._entries.get(entry_id)

    def async_entries(self, domain: str):
        return [entry for entry in self._entries.values() if entry.domain == domain]


class _Hass:
    def __init__(self) -> None:
        self.data: dict = {}
        self.config_entries = _ConfigEntries()
        self.services = _Services(self)

    def extract(self, service_call: _ServiceCall) -> set[str]:
        device_id = service_call.data.get("device_id")
        return set(self.data.get("devices", {}).get(device_id, set()))


class _Table:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def async_upload_pattern(self, *, name, path=None, thr=None):
        self.calls.append(("upload_pattern", name, path, thr))

    async def async_delete_pattern(self, *, pattern_id=None, name=None):
        self.calls.append(("delete_pattern", pattern_id, name))

    async def async_rename_pattern(self, pattern_id, name):
        self.calls.append(("rename_pattern", pattern_id, name))

    async def async_ai_draw(self, prompt, *, name=None, play=False):
        self.calls.append(("ai_draw", prompt, name, play))

    async def async_generate_pattern(self, kind, params, *, name=None, play=False):
        self.calls.append(("generate_pattern", kind, name, play, params))

    async def async_add_gallery_design(self, name, *, play=False):
        self.calls.append(("add_gallery_design", name, play))

    async def async_import_pattern_url(self, url):
        self.calls.append(("import_pattern_url", url))

    async def async_set_favorite(self, name, on):
        self.calls.append(("set_favorite", name, on))


def _install_fakes() -> None:
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = _Hass
    core.ServiceCall = _ServiceCall

    class SupportsResponse:
        OPTIONAL = "optional"

    core.SupportsResponse = SupportsResponse
    exceptions = types.ModuleType("homeassistant.exceptions")

    class ServiceValidationError(Exception):
        pass

    exceptions.ServiceValidationError = ServiceValidationError
    helpers = types.ModuleType("homeassistant.helpers")
    config_validation = types.ModuleType("homeassistant.helpers.config_validation")

    def _string(value):
        if not isinstance(value, str):
            raise vol.Invalid("expected a string")
        return value

    def _boolean(value):
        if not isinstance(value, bool):
            raise vol.Invalid("expected a boolean")
        return value

    def _positive_int(value):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise vol.Invalid("expected a positive int")
        return value

    config_validation.string = _string
    config_validation.boolean = _boolean
    config_validation.positive_int = _positive_int
    service = types.ModuleType("homeassistant.helpers.service")

    async def async_extract_config_entry_ids(service_call, expand_group=True):
        # The 2026 signature. The first argument is the call, not hass.
        return service_call.hass.extract(service_call)

    service.async_extract_config_entry_ids = async_extract_config_entry_ids
    homeassistant = types.ModuleType("homeassistant")
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    for name, module in {
        "homeassistant": homeassistant,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.config_validation": config_validation,
        "homeassistant.helpers.service": service,
    }.items():
        sys.modules[name] = module

    class DriftCoordinator:
        pass

    coordinator = types.ModuleType("custom_components.homedics_drift.coordinator")
    coordinator.DriftCoordinator = _Table
    # The handler checks isinstance(runtime, DriftCoordinator). Use the fake class.
    sys.modules["custom_components.homedics_drift.coordinator"] = coordinator
    sys.modules.pop("custom_components.homedics_drift.services", None)


@pytest.fixture
def services():
    _install_fakes()
    from custom_components.homedics_drift import services as service_mod

    return service_mod


def test_each_service_reaches_its_coordinator(services) -> None:
    hass = _Hass()
    table = _Table()
    hass.config_entries.add("entry-1", table)
    hass.data["devices"] = {"device-1": {"entry-1"}}
    calls = [
        ("upload_pattern", {"device_id": "device-1", "name": "Spiral", "thr": "0 0\n1 1\n"}),
        ("delete_pattern", {"device_id": "device-1", "pattern_id": 50001}),
        ("rename_pattern", {"device_id": "device-1", "pattern_id": 50001, "name": "Evening"}),
        ("ai_draw", {"device_id": "device-1", "prompt": "a star", "play": False}),
        ("generate_pattern", {"device_id": "device-1", "type": "spiral", "play": False}),
        ("add_gallery_design", {"device_id": "device-1", "name": "Drift Away", "play": True}),
        ("import_pattern_url", {"device_id": "device-1", "url": "https://example.com/a.thr"}),
        ("set_favorite", {"device_id": "device-1", "name": "Drift Away", "favorite": True}),
    ]
    async def _run() -> None:
        await services.async_setup_services(hass)
        for service, data in calls:
            await hass.services.async_call("homedics_drift", service, data)

    asyncio.run(_run())
    kinds = [item[0] for item in table.calls]
    assert kinds == [name for name, _data in calls]
    gallery = table.calls[5]
    assert gallery == ("add_gallery_design", "Drift Away", True)


def test_two_tables_are_refused(services) -> None:
    hass = _Hass()
    hass.config_entries.add("one", _Table())
    hass.config_entries.add("two", _Table())

    async def _run() -> None:
        await services.async_setup_services(hass)
        with pytest.raises(Exception, match="Choose one Drift table"):
            await hass.services.async_call(
                "homedics_drift",
                "add_gallery_design",
                {"name": "Drift Away"},
            )

    asyncio.run(_run())
