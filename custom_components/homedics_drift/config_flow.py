"""Config flow for HoMedics Drift tables discovered over Bluetooth."""

from __future__ import annotations

from typing import Any

import probatio
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_current_scanners,
    async_discovered_service_info,
    async_scanner_devices_by_address,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_CLEAN_BEFORE_AI,
    CONF_CONVERSATION_AGENT,
    CONF_PHOTO_CAMERA,
    CONF_PREFERRED_ADAPTER,
    CONF_WEATHER_AFTER_PATTERN,
    CONF_WEATHER_ALERT,
    CONF_WEATHER_COLD,
    CONF_WEATHER_COOLDOWN_MIN,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_HEAVY,
    CONF_WEATHER_HOT,
    CONF_WEATHER_ROTATION,
    CONF_WEATHER_UNIT,
    CONF_WEATHER_WIND,
    DOMAIN,
)
from .drawing import conversation_dropdown
from .preferred_adapter import (
    PREFERRED_ADAPTER_AUTO,
    preferred_adapter_label,
    preferred_adapter_value,
)
from .protocol import is_drift_name, normalize_advertised_name
from .weather import (
    cold_threshold_value,
    heavy_probability_value,
    hot_threshold_value,
    temperature_threshold_unit,
    weather_options_from,
    wind_threshold_unit,
    wind_threshold_value,
)


def _ai_task_dropdown(hass: Any) -> list[dict[str, str]]:
    """Every AI Task entity, named so the dropdown is obvious."""
    try:
        entity_ids = sorted(hass.states.async_entity_ids("ai_task"))
    except Exception:
        return []
    options: list[dict[str, str]] = []
    for entity_id in entity_ids:
        try:
            state = hass.states.get(entity_id)
        except Exception:
            state = None
        friendly = getattr(state, "name", None) or entity_id
        if state is None or state.state == "unavailable":
            friendly = f"{friendly} (unavailable)"
        options.append({"value": entity_id, "label": f"{friendly} — {entity_id}"})
    return options


def _conversation_agent_dropdown(hass: Any) -> list[dict[str, str]]:
    """Conversation entities other than the built-in agent, which cannot draw."""
    return conversation_dropdown(hass)


def _drift_name(discovery: BluetoothServiceInfoBleak) -> str | None:
    """Return the trimmed KS name, checking the fields proxies actually fill."""
    advertisement = getattr(discovery, "advertisement", None)
    device = getattr(discovery, "device", None)
    for candidate in (
        getattr(discovery, "name", None),
        getattr(advertisement, "local_name", None),
        getattr(device, "name", None),
    ):
        if is_drift_name(candidate):
            return normalize_advertised_name(candidate)
    return None



def _preferred_adapter_dropdown(
    hass: Any, table_address: str, current: str
) -> list[dict[str, str]]:
    """Connectable scanners, labeled with name, source, and RSSI when known."""
    options: list[dict[str, str]] = [
        {"value": PREFERRED_ADAPTER_AUTO, "label": "Automatic"}
    ]
    rssi_by: dict[str, int] = {}
    try:
        if table_address:
            for item in async_scanner_devices_by_address(
                hass, table_address, connectable=True
            ):
                scanner = getattr(item, "scanner", None)
                source = str(getattr(scanner, "source", "") or "").strip()
                rssi = getattr(getattr(item, "advertisement", None), "rssi", None)
                if source and rssi is not None:
                    try:
                        rssi_by[source.lower()] = int(rssi)
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass
    seen = {PREFERRED_ADAPTER_AUTO}
    try:
        scanners = list(async_current_scanners(hass))
    except Exception:
        scanners = []
    rows: list[tuple[str, str, int | None]] = []
    for scanner in scanners:
        if not getattr(scanner, "connectable", True):
            continue
        source = str(getattr(scanner, "source", "") or "").strip()
        if not source:
            continue
        name = str(
            getattr(scanner, "name", None)
            or getattr(scanner, "adapter", None)
            or source
        )
        rows.append((name, source, rssi_by.get(source.lower())))
    rows.sort(key=lambda row: (row[0].lower(), row[1].lower()))
    for name, source, rssi in rows:
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        options.append(
            {
                "value": source,
                "label": preferred_adapter_label(name, source, rssi),
            }
        )
    chosen = preferred_adapter_value(current)
    if chosen != PREFERRED_ADAPTER_AUTO and chosen.lower() not in seen:
        options.append(
            {"value": chosen, "label": preferred_adapter_label(chosen, chosen)}
        )
    return options


class DriftOptionsFlow(OptionsFlow):
    """AI drawing and weather drawing. No API key is stored."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose an assistant, and the weather entity that draws the forecast."""
        if user_input is not None:
            weather = weather_options_from(user_input)
            cleaned: dict[str, Any] = {
                CONF_PREFERRED_ADAPTER: preferred_adapter_value(
                    user_input.get(CONF_PREFERRED_ADAPTER)
                ),
                CONF_CLEAN_BEFORE_AI: bool(user_input.get(CONF_CLEAN_BEFORE_AI, True)),
                CONF_WEATHER_UNIT: weather[CONF_WEATHER_UNIT],
                CONF_WEATHER_ROTATION: weather[CONF_WEATHER_ROTATION],
                CONF_WEATHER_AFTER_PATTERN: weather[CONF_WEATHER_AFTER_PATTERN],
                CONF_WEATHER_COOLDOWN_MIN: weather[CONF_WEATHER_COOLDOWN_MIN],
                CONF_WEATHER_WIND: user_input.get(CONF_WEATHER_WIND),
                CONF_WEATHER_HOT: user_input.get(CONF_WEATHER_HOT),
                CONF_WEATHER_COLD: user_input.get(CONF_WEATHER_COLD),
                CONF_WEATHER_HEAVY: user_input.get(CONF_WEATHER_HEAVY),
            }
            for key in (CONF_AI_TASK_ENTITY, CONF_CONVERSATION_AGENT):
                value = user_input.get(key, self.config_entry.options.get(key))
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value.strip()
            entity = weather[CONF_WEATHER_ENTITY]
            if isinstance(entity, str) and entity.strip():
                cleaned[CONF_WEATHER_ENTITY] = entity.strip()
            camera = user_input.get(CONF_PHOTO_CAMERA)
            if isinstance(camera, str) and camera.strip():
                cleaned[CONF_PHOTO_CAMERA] = camera.strip()
            alert = user_input.get(CONF_WEATHER_ALERT, "")
            if isinstance(alert, str) and alert.strip():
                cleaned[CONF_WEATHER_ALERT] = alert.strip()
            return self.async_create_entry(title="", data=cleaned)
        current = self.config_entry.options
        weather = weather_options_from(current)
        try:
            task_options = _ai_task_dropdown(self.hass)
        except Exception:
            task_options = []
        try:
            agent_options = _conversation_agent_dropdown(self.hass)
        except Exception:
            agent_options = []
        try:
            adapter_options = _preferred_adapter_dropdown(
                self.hass,
                str(self.config_entry.data.get(CONF_ADDRESS, "") or ""),
                preferred_adapter_value(current.get(CONF_PREFERRED_ADAPTER)),
            )
        except Exception:
            adapter_options = [
                {"value": PREFERRED_ADAPTER_AUTO, "label": "Automatic"}
            ]
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_PREFERRED_ADAPTER,
                default=preferred_adapter_value(current.get(CONF_PREFERRED_ADAPTER)),
            ): selector.selector(
                {
                    "select": {
                        "options": adapter_options,
                        "mode": "dropdown",
                        "custom_value": False,
                    }
                }
            ),
            vol.Required(
                CONF_CLEAN_BEFORE_AI,
                default=current.get(CONF_CLEAN_BEFORE_AI, True),
            ): selector.selector({"boolean": {}})
        }
        camera_current = current.get(CONF_PHOTO_CAMERA, "")
        if isinstance(camera_current, str) and camera_current.strip():
            camera_key: Any = vol.Optional(
                CONF_PHOTO_CAMERA,
                description={"suggested_value": camera_current.strip()},
            )
        else:
            camera_key = vol.Optional(CONF_PHOTO_CAMERA)
        schema[camera_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="camera")
        )
        if task_options:
            schema[
                vol.Optional(
                    CONF_AI_TASK_ENTITY,
                    description={"suggested_value": current.get(CONF_AI_TASK_ENTITY, "")},
                )
            ] = selector.selector(
                {
                    "select": {
                        "options": task_options,
                        "mode": "dropdown",
                        "custom_value": False,
                    }
                }
            )
        if agent_options:
            schema[
                vol.Optional(
                    CONF_CONVERSATION_AGENT,
                    description={
                        "suggested_value": current.get(CONF_CONVERSATION_AGENT, "")
                    },
                )
            ] = selector.selector(
                {
                    "select": {
                        "options": agent_options,
                        "mode": "dropdown",
                        "custom_value": False,
                    }
                }
            )
        entity_key: Any
        if weather[CONF_WEATHER_ENTITY]:
            entity_key = vol.Optional(
                CONF_WEATHER_ENTITY,
                description={"suggested_value": weather[CONF_WEATHER_ENTITY]},
            )
        else:
            entity_key = vol.Optional(CONF_WEATHER_ENTITY)
        schema[entity_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather")
        )
        schema[
            vol.Required(
                CONF_WEATHER_UNIT,
                default=weather[CONF_WEATHER_UNIT],
            )
        ] = selector.selector(
            {
                "select": {
                    "options": ["auto", "F", "C"],
                    "mode": "dropdown",
                }
            }
        )
        schema[
            vol.Required(
                CONF_WEATHER_ROTATION,
                default=weather[CONF_WEATHER_ROTATION],
            )
        ] = selector.selector(
            {
                "number": {
                    "min": 0,
                    "max": 359,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": "°",
                }
            }
        )
        schema[
            vol.Required(
                CONF_WEATHER_AFTER_PATTERN,
                default=weather[CONF_WEATHER_AFTER_PATTERN],
            )
        ] = selector.selector({"boolean": {}})
        schema[
            vol.Required(
                CONF_WEATHER_COOLDOWN_MIN,
                default=weather[CONF_WEATHER_COOLDOWN_MIN],
            )
        ] = selector.selector(
            {
                "number": {
                    "min": 0,
                    "max": 1440,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": "min",
                }
            }
        )
        entity_id = weather[CONF_WEATHER_ENTITY] if isinstance(weather[CONF_WEATHER_ENTITY], str) else ""
        reported = None
        if entity_id:
            state = self.hass.states.get(entity_id)
            attributes = getattr(state, "attributes", None) if state is not None else None
            if isinstance(attributes, dict):
                reported = attributes.get("temperature_unit")
        speed_unit = wind_threshold_unit(weather[CONF_WEATHER_UNIT], reported)
        degree_unit = "°C" if temperature_threshold_unit(weather[CONF_WEATHER_UNIT], reported) == "C" else "°F"
        schema[
            vol.Required(
                CONF_WEATHER_WIND,
                default=wind_threshold_value(weather[CONF_WEATHER_WIND], speed_unit),
            )
        ] = selector.selector(
            {
                "number": {
                    "min": 0,
                    "max": 200,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": speed_unit,
                }
            }
        )
        schema[
            vol.Required(
                CONF_WEATHER_HOT,
                default=hot_threshold_value(
                    weather[CONF_WEATHER_HOT],
                    "C" if degree_unit == "°C" else "F",
                ),
            )
        ] = selector.selector(
            {
                "number": {
                    "min": -40,
                    "max": 140,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": degree_unit,
                }
            }
        )
        schema[
            vol.Required(
                CONF_WEATHER_COLD,
                default=cold_threshold_value(
                    weather[CONF_WEATHER_COLD],
                    "C" if degree_unit == "°C" else "F",
                ),
            )
        ] = selector.selector(
            {
                "number": {
                    "min": -80,
                    "max": 80,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": degree_unit,
                }
            }
        )
        schema[
            vol.Required(
                CONF_WEATHER_HEAVY,
                default=heavy_probability_value(weather[CONF_WEATHER_HEAVY]),
            )
        ] = selector.selector(
            {
                "number": {
                    "min": 0,
                    "max": 100,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": "%",
                }
            }
        )
        alert_current = weather[CONF_WEATHER_ALERT]
        if isinstance(alert_current, str) and alert_current.strip():
            alert_key: Any = vol.Optional(
                CONF_WEATHER_ALERT,
                description={"suggested_value": alert_current.strip()},
            )
        else:
            alert_key = vol.Optional(CONF_WEATHER_ALERT)
        schema[alert_key] = selector.EntitySelector(
            selector.EntitySelectorConfig(
                filter=[
                    selector.EntityFilterSelectorConfig(domain="binary_sensor"),
                    selector.EntityFilterSelectorConfig(domain="sensor"),
                ]
            )
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))


class DriftConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Drift table from discovery or a manual pick list."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> DriftOptionsFlow:
        """Let the user pick an AI Task entity. The argument is unused."""
        del config_entry
        return DriftOptionsFlow()

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._name: str | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device matched by the KS* local-name filter."""
        name = _drift_name(discovery_info)
        if name is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self._name = name
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered table."""
        assert self._discovery is not None
        assert self._name is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_ADDRESS: self._discovery.address},
            )
        placeholders = {"name": self._name}
        self.context["title_placeholders"] = placeholders
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders=placeholders,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer every visible Drift table, with no address typed by hand."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered[address],
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids(include_ignore=False)
        for discovery in async_discovered_service_info(self.hass, connectable=True):
            address = discovery.address
            if address in current or address in self._discovered:
                continue
            name = _drift_name(discovery)
            if name is not None:
                self._discovered[address] = f"{name} ({address})"

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_ADDRESS): probatio.In(self._discovered)}
            ),
        )
