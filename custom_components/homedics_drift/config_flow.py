"""Config flow for HoMedics Drift tables discovered over Bluetooth."""

from __future__ import annotations

from typing import Any

import probatio
import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector

from .const import (
    CONF_AI_ART_STYLE,
    CONF_AI_TASK_ENTITY,
    CONF_CLEAN_BEFORE_AI,
    CONF_CONVERSATION_AGENT,
    DOMAIN,
)
from .drawing import conversation_dropdown
from .protocol import is_drift_name, normalize_advertised_name


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


class DriftOptionsFlow(OptionsFlow):
    """Optional AI Task entity. No API key is stored."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which assistant draws a prompt, if the user has one."""
        if user_input is not None:
            style = user_input.get(CONF_AI_ART_STYLE, "contours")
            cleaned: dict[str, Any] = {
                CONF_CLEAN_BEFORE_AI: bool(user_input.get(CONF_CLEAN_BEFORE_AI, True)),
                CONF_AI_ART_STYLE: style if style in {"contours", "spiral", "line"} else "contours",
            }
            for key in (CONF_AI_TASK_ENTITY, CONF_CONVERSATION_AGENT):
                value = user_input.get(key, self.config_entry.options.get(key))
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value.strip()
            return self.async_create_entry(title="", data=cleaned)
        current = self.config_entry.options
        try:
            task_options = _ai_task_dropdown(self.hass)
        except Exception:
            task_options = []
        try:
            agent_options = _conversation_agent_dropdown(self.hass)
        except Exception:
            agent_options = []
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CLEAN_BEFORE_AI,
                default=current.get(CONF_CLEAN_BEFORE_AI, True),
            ): selector.selector({"boolean": {}}),
            vol.Required(
                CONF_AI_ART_STYLE,
                default=current.get(CONF_AI_ART_STYLE, "contours"),
            ): selector.selector(
                {
                    "select": {
                        "options": [
                            {"value": "contours", "label": "Contours"},
                            {"value": "spiral", "label": "Spiral shading"},
                            {"value": "line", "label": "Line drawing"},
                        ],
                        "mode": "dropdown",
                    }
                }
            ),
        }
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
