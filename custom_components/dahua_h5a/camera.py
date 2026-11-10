"""Camera platform for Dahua H5A (5MP RTSP stream + snapshots + PTZ entity services)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_STREAM_SUBTYPE,
    DEFAULT_STREAM_SUBTYPE,
    SERVICE_PTZ_GOTO_PRESET,
    SERVICE_PTZ_MOVE,
    SERVICE_PTZ_REMOVE_PRESET,
    SERVICE_PTZ_SET_PRESET,
    SERVICE_TRIGGER_SIREN,
)
from .coordinator import DahuaH5ACoordinator
from .entity import DahuaH5AEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dahua H5A camera entity and register PTZ/siren entity services."""
    coordinator: DahuaH5ACoordinator = entry.runtime_data
    async_add_entities([DahuaH5ACamera(coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_PTZ_MOVE,
        {
            vol.Required("direction"): vol.In(
                ["up", "down", "left", "right", "left_up", "right_up", "left_down", "right_down"]
            ),
            vol.Optional("speed", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
            vol.Optional("duration", default=0.5): vol.All(
                vol.Coerce(float), vol.Range(min=0.1, max=10.0)
            ),
        },
        "async_ptz_move",
    )
    platform.async_register_entity_service(
        SERVICE_PTZ_GOTO_PRESET,
        {
            vol.Required("preset_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
        },
        "async_ptz_goto_preset",
    )
    platform.async_register_entity_service(
        SERVICE_PTZ_SET_PRESET,
        {
            vol.Required("preset_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            vol.Required("name"): str,
        },
        "async_ptz_set_preset",
    )
    platform.async_register_entity_service(
        SERVICE_PTZ_REMOVE_PRESET,
        {
            vol.Required("preset_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
        },
        "async_ptz_remove_preset",
    )
    platform.async_register_entity_service(
        SERVICE_TRIGGER_SIREN,
        {
            vol.Optional("duration", default=10): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=60)
            ),
        },
        "async_trigger_siren",
    )


class DahuaH5ACamera(DahuaH5AEntity, Camera):
    """Representation of a Dahua H5A 5MP RTSP camera."""

    _attr_translation_key = "camera"
    _attr_supported_features = CameraEntityFeature.STREAM | CameraEntityFeature.ON_OFF

    def __init__(self, coordinator: DahuaH5ACoordinator) -> None:
        """Initialize the camera entity."""
        DahuaH5AEntity.__init__(self, coordinator, "camera")
        Camera.__init__(self)

    @property
    def is_on(self) -> bool:
        """Return True when the lens is open (privacy mode is OFF)."""
        return not self.coordinator.data.privacy_mode

    @property
    def is_recording(self) -> bool:
        """Return True when the camera is actively recording/streaming."""
        return not self.coordinator.data.privacy_mode

    @property
    def motion_detection_enabled(self) -> bool:
        """Return True if motion detection is enabled."""
        return self.coordinator.data.motion_detection

    async def async_stream_source(self) -> str | None:
        """Return the RTSP stream URL when privacy mode is disabled."""
        if self.coordinator.data.privacy_mode:
            return None
        subtype = int(
            self.coordinator.config_entry.options.get(
                CONF_STREAM_SUBTYPE, DEFAULT_STREAM_SUBTYPE
            )
        )
        return self.coordinator.client.get_rtsp_url(subtype=subtype)

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still JPEG snapshot from the camera."""
        if self.coordinator.data.privacy_mode:
            return None
        subtype = int(
            self.coordinator.config_entry.options.get(
                CONF_STREAM_SUBTYPE, DEFAULT_STREAM_SUBTYPE
            )
        )
        try:
            return await self.coordinator.client.capture_snapshot(subtype=subtype)
        except Exception:
            return None

    async def async_turn_on(self) -> None:
        """Open the physical privacy shutter (disable privacy mode)."""
        await self.coordinator.async_execute(
            self.coordinator.client.set_privacy_mode, False
        )

    async def async_turn_off(self) -> None:
        """Close the physical privacy shutter (enable privacy mode)."""
        await self.coordinator.async_execute(
            self.coordinator.client.set_privacy_mode, True
        )

    async def async_enable_motion_detection(self) -> None:
        """Enable motion detection."""
        await self.coordinator.async_execute(
            self.coordinator.client.set_motion_detection, True
        )

    async def async_disable_motion_detection(self) -> None:
        """Disable motion detection."""
        await self.coordinator.async_execute(
            self.coordinator.client.set_motion_detection, False
        )

    async def async_ptz_move(
        self, direction: str, speed: int = 4, duration: float = 0.5
    ) -> None:
        """Move PTZ in the given direction."""
        await self.coordinator.async_execute(
            self.coordinator.client.ptz_step,
            direction,
            speed=speed,
            duration=duration,
        )

    async def async_ptz_goto_preset(self, preset_id: int) -> None:
        """Move PTZ to a saved preset."""
        await self.coordinator.async_execute(
            self.coordinator.client.ptz_goto_preset, preset_id
        )

    async def async_ptz_set_preset(self, preset_id: int, name: str) -> None:
        """Save the current position as a PTZ preset."""
        await self.coordinator.async_execute(
            self.coordinator.client.ptz_set_preset, preset_id, name
        )

    async def async_ptz_remove_preset(self, preset_id: int) -> None:
        """Delete a PTZ preset."""
        await self.coordinator.async_execute(
            self.coordinator.client.ptz_remove_preset, preset_id
        )

    async def async_trigger_siren(self, duration: int = 10) -> None:
        """Trigger the built-in alarm siren."""
        await self.coordinator.async_execute(
            self.coordinator.client.set_siren_config, duration=duration
        )
        await self.coordinator.async_execute(
            self.coordinator.client.trigger_siren, True
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra camera attributes (PTZ coordinates, presets, AI states)."""
        state = self.coordinator.data
        return {
            "privacy_mode": state.privacy_mode,
            "human_detection": state.human_detection,
            "pet_detection": state.pet_detection,
            "smart_tracking": state.smart_track,
            "ir_mode": state.ir_mode,
            "day_night_mode": state.day_night_mode,
            "ptz_action": state.ptz.action,
            "ptz_pan": state.ptz.pan,
            "ptz_tilt": state.ptz.tilt,
            "ptz_zoom": state.ptz.zoom,
            "presets": {p.index: p.name for p in state.presets},
        }
