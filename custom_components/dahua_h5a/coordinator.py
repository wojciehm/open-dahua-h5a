"""DataUpdateCoordinator and real-time event subscriber for Dahua H5A cameras."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CameraEvent, CameraState, DahuaH5AClient, DahuaH5AError, DeviceInfo
from .const import (
    CONF_RTSP_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_RTSP_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

EVENT_COOLDOWN_SECONDS = 15.0


class DahuaH5ACoordinator(DataUpdateCoordinator[CameraState]):
    """Coordinate periodic state polling and real-time TCP 37777 push events per camera."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a single camera entry."""
        self.config_entry = entry
        self.client = DahuaH5AClient(
            host=entry.data[CONF_HOST],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
            rtsp_port=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
        )
        self.device_info = DeviceInfo()
        self._unsub_events = self.client.register_event_callback(self._on_camera_event)
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_HOST]}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._lock = asyncio.Lock()
        self._event_attached = False
        self.active_events: dict[str, float] = {}
        self.last_event: CameraEvent | None = None

    async def _ensure_connected(self) -> None:
        """Connect to the camera and attach event listener if not already connected."""
        if not self.client.protocol.is_connected:
            self._event_attached = False
            await self.client.connect()
            self.device_info = await self.client.get_device_info()
        if not self._event_attached:
            try:
                await self.client.attach_events()
                self._event_attached = True
            except DahuaH5AError as err:
                _LOGGER.debug("Could not attach event stream yet: %s", err)

    @callback
    def _on_camera_event(self, event: CameraEvent) -> None:
        """Handle real-time push event from TCP 37777 client.notifyEventStream."""
        now = time.monotonic()
        self.last_event = event
        action = event.action.lower()
        if action in ("start", "pulse"):
            self.active_events[event.code] = now + EVENT_COOLDOWN_SECONDS
        elif action == "stop":
            self.active_events.pop(event.code, None)

        self.hass.bus.async_fire(
            f"{DOMAIN}_event",
            {
                "entry_id": self.config_entry.entry_id,
                "host": self.config_entry.data[CONF_HOST],
                "code": event.code,
                "action": event.action,
                "index": event.index,
                "data": event.data,
            },
        )
        self.async_update_listeners()

    def is_event_active(self, codes: tuple[str, ...]) -> bool:
        """Return True if any of the given event codes is currently active."""
        now = time.monotonic()
        for code in codes:
            expiry = self.active_events.get(code)
            if expiry and expiry > now:
                return True
        if self.data:
            if "VideoMotion" in codes and self.data.motion_active:
                return True
            if "SmartMotionHuman" in codes and self.data.human_active:
                return True
            if "SmartMotionAnimal" in codes and self.data.pet_active:
                return True
            if "AudioMutation" in codes and self.data.audio_alarm_active:
                return True
        return False

    async def _async_update_data(self) -> CameraState:
        """Fetch the latest camera state over TCP 37777, reconnecting if needed."""
        async with self._lock:
            try:
                await self._ensure_connected()
                return await self.client.get_full_state()
            except Exception as err:
                _LOGGER.debug(
                    "Reconnecting to Dahua H5A (%s) after error: %s",
                    self.config_entry.data[CONF_HOST],
                    err,
                )
                try:
                    await self.client.close()
                    self._event_attached = False
                    await self._ensure_connected()
                    return await self.client.get_full_state()
                except Exception as retry_err:
                    raise UpdateFailed(
                        f"Error communicating with Dahua H5A ({self.config_entry.data[CONF_HOST]}): {retry_err}"
                    ) from retry_err

    async def async_execute(self, coro_func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute a camera control command safely and refresh state."""
        async with self._lock:
            await self._ensure_connected()
            result = await coro_func(*args, **kwargs)
        await self.async_request_refresh()
        return result

    async def async_shutdown(self) -> None:
        """Close the persistent TCP 37777 connection cleanly."""
        if self._unsub_events:
            self._unsub_events()
            self._unsub_events = None
        await self.client.close()
