"""Switch platform for Dahua H5A camera controls."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CameraState, DahuaH5AClient
from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


@dataclass(frozen=True, kw_only=True)
class DahuaH5ASwitchDescription(SwitchEntityDescription):
    """Describe a Dahua H5A switch entity."""

    value_fn: Callable[[CameraState], bool]
    turn_on_fn: Callable[[DahuaH5AClient], Awaitable[bool]]
    turn_off_fn: Callable[[DahuaH5AClient], Awaitable[bool]]


SWITCH_DESCRIPTIONS: tuple[DahuaH5ASwitchDescription, ...] = (
    DahuaH5ASwitchDescription(
        key="privacy_mode",
        translation_key="privacy_mode",
        icon="mdi:eye-off",
        value_fn=lambda s: s.privacy_mode,
        turn_on_fn=lambda c: c.set_privacy_mode(True),
        turn_off_fn=lambda c: c.set_privacy_mode(False),
    ),
    DahuaH5ASwitchDescription(
        key="human_detection",
        translation_key="human_detection",
        icon="mdi:human-greeting-variant",
        value_fn=lambda s: s.human_detection,
        turn_on_fn=lambda c: c.set_human_detection(True),
        turn_off_fn=lambda c: c.set_human_detection(False),
    ),
    DahuaH5ASwitchDescription(
        key="pet_detection",
        translation_key="pet_detection",
        icon="mdi:paw",
        value_fn=lambda s: s.pet_detection,
        turn_on_fn=lambda c: c.set_pet_detection(True),
        turn_off_fn=lambda c: c.set_pet_detection(False),
    ),
    DahuaH5ASwitchDescription(
        key="smart_tracking",
        translation_key="smart_tracking",
        icon="mdi:radar",
        value_fn=lambda s: s.smart_track,
        turn_on_fn=lambda c: c.set_smart_track(True),
        turn_off_fn=lambda c: c.set_smart_track(False),
    ),
    DahuaH5ASwitchDescription(
        key="motion_detection",
        translation_key="motion_detection",
        icon="mdi:motion-sensor",
        value_fn=lambda s: s.motion_detection,
        turn_on_fn=lambda c: c.set_motion_detection(True),
        turn_off_fn=lambda c: c.set_motion_detection(False),
    ),
    DahuaH5ASwitchDescription(
        key="audio_detection",
        translation_key="audio_detection",
        icon="mdi:ear-hearing",
        value_fn=lambda s: s.audio_detection,
        turn_on_fn=lambda c: c.set_audio_detection(enabled=True),
        turn_off_fn=lambda c: c.set_audio_detection(enabled=False),
    ),
    DahuaH5ASwitchDescription(
        key="status_led",
        translation_key="status_led",
        icon="mdi:led-on",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.status_led,
        turn_on_fn=lambda c: c.set_status_led(True),
        turn_off_fn=lambda c: c.set_status_led(False),
    ),
    DahuaH5ASwitchDescription(
        key="audio_encode",
        translation_key="audio_encode",
        icon="mdi:microphone",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.stream_audio_enabled,
        turn_on_fn=lambda c: c.set_stream_audio(True),
        turn_off_fn=lambda c: c.set_stream_audio(False),
    ),
    DahuaH5ASwitchDescription(
        key="mirror",
        translation_key="mirror",
        icon="mdi:flip-horizontal",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.mirror,
        turn_on_fn=lambda c: c.set_mirror_flip(mirror=True),
        turn_off_fn=lambda c: c.set_mirror_flip(mirror=False),
    ),
    DahuaH5ASwitchDescription(
        key="flip",
        translation_key="flip",
        icon="mdi:flip-vertical",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.flip,
        turn_on_fn=lambda c: c.set_mirror_flip(flip=True),
        turn_off_fn=lambda c: c.set_mirror_flip(flip=False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A switches from a config entry."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        DahuaH5ASwitch(coordinator, description)
        for description in SWITCH_DESCRIPTIONS
    )


class DahuaH5ASwitch(DahuaH5AEntity, SwitchEntity):
    """Representation of a Dahua H5A switch."""

    entity_description: DahuaH5ASwitchDescription

    def __init__(
        self,
        coordinator: DahuaH5ACoordinator,
        description: DahuaH5ASwitchDescription,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_execute(
            self.entity_description.turn_on_fn, self.coordinator.client
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_execute(
            self.entity_description.turn_off_fn, self.coordinator.client
        )
