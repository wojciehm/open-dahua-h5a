"""Sensor platform for Dahua H5A MicroSD storage and PTZ telemetry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CameraState
from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


@dataclass(frozen=True, kw_only=True)
class DahuaH5ASensorDescription(SensorEntityDescription):
    """Describe a Dahua H5A sensor entity."""

    value_fn: Callable[[CameraState], float | str | None]


SENSOR_DESCRIPTIONS: tuple[DahuaH5ASensorDescription, ...] = (
    DahuaH5ASensorDescription(
        key="sd_status",
        translation_key="sd_status",
        icon="mdi:micro-sd",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.storage.state,
    ),
    DahuaH5ASensorDescription(
        key="sd_used_percent",
        translation_key="sd_used_percent",
        icon="mdi:micro-sd",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.storage.used_percent,
    ),
    DahuaH5ASensorDescription(
        key="sd_free_gb",
        translation_key="sd_free_gb",
        icon="mdi:sd",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: round(s.storage.free_bytes / (1024**3), 2),
    ),
    DahuaH5ASensorDescription(
        key="ptz_pan",
        translation_key="ptz_pan",
        icon="mdi:pan-horizontal",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: round(s.ptz.pan, 1),
    ),
    DahuaH5ASensorDescription(
        key="ptz_tilt",
        translation_key="ptz_tilt",
        icon="mdi:pan-vertical",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: round(s.ptz.tilt, 1),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A sensors."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        DahuaH5ASensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class DahuaH5ASensor(DahuaH5AEntity, SensorEntity):
    """Representation of a Dahua H5A telemetry sensor."""

    entity_description: DahuaH5ASensorDescription

    def __init__(
        self,
        coordinator: DahuaH5ACoordinator,
        description: DahuaH5ASensorDescription,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
