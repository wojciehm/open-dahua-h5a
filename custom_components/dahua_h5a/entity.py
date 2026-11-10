"""Base entity for the Dahua H5A Home Assistant integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DahuaH5ACoordinator


class DahuaH5AEntity(CoordinatorEntity[DahuaH5ACoordinator]):
    """Base entity representing a Dahua H5A camera feature."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DahuaH5ACoordinator, key: str) -> None:
        """Initialize the entity with a unique key per camera."""
        super().__init__(coordinator)
        info = coordinator.device_info
        serial = (
            info.serial_number
            if info.serial_number and info.serial_number != "UNKNOWN"
            else coordinator.config_entry.entry_id
        )
        self._serial = serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=info.machine_name
            or f"Dahua H5A ({coordinator.config_entry.data[CONF_HOST]})",
            manufacturer=info.vendor or "Dahua",
            model=info.device_type or "DH-H5A",
            sw_version=info.software_version,
            hw_version=info.hardware_version,
            serial_number=info.serial_number,
        )
