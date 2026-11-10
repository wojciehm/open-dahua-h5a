"""Number platform for Dahua H5A audio volumes and detection sensitivity."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CameraState, DahuaH5AClient
from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


@dataclass(frozen=True, kw_only=True)
class DahuaH5ANumberDescription(NumberEntityDescription):
    """Describe a Dahua H5A number entity."""

    value_fn: Callable[[CameraState], int]
    set_value_fn: Callable[[DahuaH5AClient, int], Awaitable[bool]]


NUMBER_DESCRIPTIONS: tuple[DahuaH5ANumberDescription, ...] = (
    DahuaH5ANumberDescription(
        key="speaker_volume",
        translation_key="speaker_volume",
        icon="mdi:volume-high",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.speaker_volume,
        set_value_fn=lambda c, v: c.set_speaker_volume(v),
    ),
    DahuaH5ANumberDescription(
        key="microphone_volume",
        translation_key="microphone_volume",
        icon="mdi:microphone-settings",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.mic_volume,
        set_value_fn=lambda c, v: c.set_mic_volume(v),
    ),
    DahuaH5ANumberDescription(
        key="audio_sensitivity",
        translation_key="audio_sensitivity",
        icon="mdi:ear-hearing",
        native_min_value=1,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.audio_anomaly_sensitivity,
        set_value_fn=lambda c, v: c.set_audio_detection(enabled=True, sensitivity=v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A number entities."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        DahuaH5ANumber(coordinator, description)
        for description in NUMBER_DESCRIPTIONS
    )


class DahuaH5ANumber(DahuaH5AEntity, NumberEntity):
    """Representation of a Dahua H5A numeric slider."""

    entity_description: DahuaH5ANumberDescription

    def __init__(
        self,
        coordinator: DahuaH5ACoordinator,
        description: DahuaH5ANumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        """Return the current number value."""
        return float(self.entity_description.value_fn(self.coordinator.data))

    async def async_set_native_value(self, value: float) -> None:
        """Update the number value on the camera."""
        await self.coordinator.async_execute(
            self.entity_description.set_value_fn,
            self.coordinator.client,
            int(round(value)),
        )
