"""Config flow for HoMedics Drift tables discovered over Bluetooth."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .protocol import is_drift_name, normalize_advertised_name


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


class DriftConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Drift table from discovery or a manual pick list."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._name: str | None = None
        self._discovered: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a Bluetooth discovery, if a matcher is ever added.

        There is no manifest matcher. ``KS*`` is illegal (a pattern in the
        first three characters aborts the Bluetooth integration), and the
        UART service UUID is shared by many modules. Setup is the manual
        pick list, which keeps names that start with KS.
        """
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
