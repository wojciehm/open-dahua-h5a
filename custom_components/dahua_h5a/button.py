"""Button platform for Dahua H5A (PTZ controls, calibration, and siren)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DahuaH5AClient
from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


@dataclass(frozen=True, kw_only=True)
class DahuaH5AButtonDescription(ButtonEntityDescription):
    """Describe a Dahua H5A button entity."""

    press_fn: Callable[[DahuaH5AClient], Awaitable[bool]]


BUTTON_DESCRIPTIONS: tuple[DahuaH5AButtonDescription, ...] = (
    DahuaH5AButtonDescription(
        key="ptz_up",
        translation_key="ptz_up",
        icon="mdi:arrow-up-bold",
        press_fn=lambda c: c.ptz_step("up", speed=4, duration=0.4),
    ),
    DahuaH5AButtonDescription(
        key="ptz_down",
        translation_key="ptz_down",
        icon="mdi:arrow-down-bold",
        press_fn=lambda c: c.ptz_step("down", speed=4, duration=0.4),
    ),
    DahuaH5AButtonDescription(
        key="ptz_left",
        translation_key="ptz_left",
        icon="mdi:arrow-left-bold",
        press_fn=lambda c: c.ptz_step("left", speed=4, duration=0.4),
    ),
    DahuaH5AButtonDescription(
        key="ptz_right",
        translation_key="ptz_right",
        icon="mdi:arrow-right-bold",
        press_fn=lambda c: c.ptz_step("right", speed=4, duration=0.4),
    ),
    DahuaH5AButtonDescription(
        key="siren",
        translation_key="siren",
        icon="mdi:bullhorn",
        press_fn=lambda c: c.trigger_siren(True),
    ),
    DahuaH5AButtonDescription(
        key="ptz_calibrate",
        translation_key="ptz_calibrate",
        icon="mdi:compass-outline",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.ptz_restart(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A buttons."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        DahuaH5AButton(coordinator, description)
        for description in BUTTON_DESCRIPTIONS
    )


class DahuaH5AButton(DahuaH5AEntity, ButtonEntity):
    """Representation of a Dahua H5A action button."""

    entity_description: DahuaH5AButtonDescription

    def __init__(
        self,
        coordinator: DahuaH5ACoordinator,
        description: DahuaH5AButtonDescription,
    ) -> None:
        """Initialize the button entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Execute the button action."""
        await self.coordinator.async_execute(
            self.entity_description.press_fn, self.coordinator.client
        )
