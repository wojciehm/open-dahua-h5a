"""The Dahua H5A (Local NetSDK) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import DahuaH5ACoordinator

PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

type DahuaH5AConfigEntry = ConfigEntry[DahuaH5ACoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DahuaH5AConfigEntry) -> bool:
    """Set up a Dahua H5A camera from a UI config entry."""
    coordinator = DahuaH5ACoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    info = coordinator.device_info
    serial = (
        info.serial_number
        if info.serial_number and info.serial_number != "UNKNOWN"
        else entry.entry_id
    )
    ent_reg = er.async_get(hass)
    legacy_led_switch = ent_reg.async_get_entity_id(
        Platform.SWITCH, DOMAIN, f"{serial}_status_led"
    )
    if legacy_led_switch is not None:
        ent_reg.async_remove(legacy_led_switch)

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: DahuaH5AConfigEntry
) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DahuaH5AConfigEntry) -> bool:
    """Unload a config entry and close its TCP 37777 connection."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DahuaH5ACoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
