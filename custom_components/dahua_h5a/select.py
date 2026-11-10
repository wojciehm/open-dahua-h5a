"""Select platform for Dahua H5A (Night Vision mode & PTZ Presets)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity

NIGHT_VISION_OPTIONS = ["auto", "off", "on"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dahua H5A select entities."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities(
        [
            DahuaH5ANightVisionSelect(coordinator),
            DahuaH5APresetSelect(coordinator),
        ]
    )


class DahuaH5ANightVisionSelect(DahuaH5AEntity, SelectEntity):
    """Select entity for Night Vision IR mode (auto / off / on)."""

    _attr_translation_key = "night_vision_mode"
    _attr_icon = "mdi:weather-night"
    _attr_options = NIGHT_VISION_OPTIONS
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DahuaH5ACoordinator) -> None:
        """Initialize the night vision select entity."""
        super().__init__(coordinator, "night_vision_mode")

    @property
    def current_option(self) -> str:
        """Return the current night vision mode."""
        ir = self.coordinator.data.ir_mode.lower()
        dn = self.coordinator.data.day_night_mode.lower()
        if ir == "off" or dn == "color":
            return "off"
        if ir == "manual" or dn == "blackwhite":
            return "on"
        return "auto"

    async def async_select_option(self, option: str) -> None:
        """Change the night vision mode."""
        preset_map = {"auto": "auto", "off": "day", "on": "night"}
        await self.coordinator.async_execute(
            self.coordinator.client.set_night_vision,
            preset_map.get(option, "auto"),
        )


class DahuaH5APresetSelect(DahuaH5AEntity, SelectEntity):
    """Select entity to jump to any PTZ preset configured on the camera."""

    _attr_translation_key = "ptz_preset"
    _attr_icon = "mdi:cctv"

    def __init__(self, coordinator: DahuaH5ACoordinator) -> None:
        """Initialize the PTZ preset selector."""
        super().__init__(coordinator, "ptz_preset")
        self._last_selected: str | None = None

    @property
    def options(self) -> list[str]:
        """Return dynamic list of presets from the camera."""
        presets = self.coordinator.data.presets
        if not presets:
            return ["1: Preset 1"]
        return [f"{p.index}: {p.name}" for p in presets]

    @property
    def current_option(self) -> str | None:
        """Return the most recently selected preset or the first available."""
        opts = self.options
        if self._last_selected in opts:
            return self._last_selected
        return opts[0] if opts else None

    async def async_select_option(self, option: str) -> None:
        """Move the camera PTZ to the chosen preset."""
        self._last_selected = option
        preset_id_str = option.split(":", 1)[0].strip()
        preset_id = int(preset_id_str)
        await self.coordinator.async_execute(
            self.coordinator.client.ptz_goto_preset, preset_id
        )
