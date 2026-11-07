"""Shared device info for Drift entities."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import DriftCoordinator
from .protocol import DriftState


class DriftEntity(CoordinatorEntity[DriftCoordinator]):
    """A Drift entity that is unavailable until the table has reported state."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DriftCoordinator) -> None:
        """Attach the coordinator."""
        super().__init__(coordinator)

    @property
    def available(self) -> bool:
        """Unavailable while the table is unplugged or not yet heard from."""
        return super().available and self.coordinator.data is not None

    @property
    def device_info(self) -> DeviceInfo:
        """Identify the sand table. Firmware versions arrive with the first state."""
        state = self.coordinator.data
        versions: list[str] = []
        if isinstance(state, DriftState):
            if state.controller_version:
                versions.append(state.controller_version)
            if state.driver_version:
                versions.append(state.driver_version)
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, self.coordinator.address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self.coordinator.name,
            sw_version=" / ".join(versions) or None,
        )

    @property
    def _state(self) -> DriftState:
        state = self.coordinator.data
        assert state is not None
        return state
