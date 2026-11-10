"""Binary sensor platform for Dahua H5A real-time events and privacy state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


@dataclass(frozen=True, kw_only=True)
class DahuaH5ABinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Dahua H5A binary sensor."""

    is_on_fn: Callable[[DahuaH5ACoordinator], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[DahuaH5ABinarySensorDescription, ...] = (
    DahuaH5ABinarySensorDescription(
        key="motion",
        translation_key="motion",
        device_class=BinarySensorDeviceClass.MOTION,
        is_on_fn=lambda coord: coord.is_event_active(
            ("VideoMotion", "SmartMotionHuman", "SmartMotionVehicle")
        ),
    ),
    DahuaH5ABinarySensorDescription(
        key="human_detected",
        translation_key="human_detected",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:human-greeting-variant",
        is_on_fn=lambda coord: coord.is_event_active(
            ("SmartMotionHuman", "CrossLineDetection", "CrossRegionDetection")
        ),
    ),
    DahuaH5ABinarySensorDescription(
        key="sound_detected",
        translation_key="sound_detected",
        device_class=BinarySensorDeviceClass.SOUND,
        icon="mdi:ear-hearing",
        is_on_fn=lambda coord: coord.is_event_active(
            ("AudioMutation", "AudioAnomaly", "BabyCry")
        ),
    ),
    DahuaH5ABinarySensorDescription(
        key="privacy_active",
        translation_key="privacy_active",
        icon="mdi:eye-off-outline",
        is_on_fn=lambda coord: bool(coord.data and coord.data.privacy_mode),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A binary sensors."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        DahuaH5ABinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class DahuaH5ABinarySensor(DahuaH5AEntity, BinarySensorEntity):
    """Representation of a Dahua H5A binary sensor."""

    entity_description: DahuaH5ABinarySensorDescription

    def __init__(
        self,
        coordinator: DahuaH5ACoordinator,
        description: DahuaH5ABinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is active."""
        return self.entity_description.is_on_fn(self.coordinator)
