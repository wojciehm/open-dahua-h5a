"""Config flow for Dahua H5A (Local NetSDK) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .api import (
    DahuaAuthError,
    DahuaConnectionError,
    DahuaH5AClient,
    DahuaH5AError,
    DeviceInfo,
)
from .const import (
    CONF_RTSP_PORT,
    CONF_SCAN_INTERVAL,
    CONF_STREAM_SUBTYPE,
    DEFAULT_PORT,
    DEFAULT_RTSP_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STREAM_SUBTYPE,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_connection(user_input: dict[str, Any]) -> DeviceInfo:
    """Connect to the camera on TCP 37777, authenticate, and fetch device metadata."""
    client = DahuaH5AClient(
        host=user_input[CONF_HOST].strip(),
        username=user_input[CONF_USERNAME].strip(),
        password=user_input[CONF_PASSWORD],
        port=int(user_input.get(CONF_PORT, DEFAULT_PORT)),
        rtsp_port=int(user_input.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)),
    )
    async with client:
        return await client.get_device_info()


class DahuaH5AConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow for adding and reconfiguring Dahua H5A cameras."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return DahuaH5AOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step where the user enters IP, ports, and credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_connection(user_input)
            except DahuaAuthError:
                errors["base"] = "invalid_auth"
            except (DahuaConnectionError, DahuaH5AError, TimeoutError, OSError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Dahua H5A camera")
                errors["base"] = "unknown"
            else:
                unique_id = (
                    info.serial_number
                    if info.serial_number and info.serial_number != "UNKNOWN"
                    else f"{user_input[CONF_HOST].strip()}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                title = f"{info.machine_name} ({user_input[CONF_HOST].strip()})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PORT: int(user_input.get(CONF_PORT, DEFAULT_PORT)),
                        CONF_RTSP_PORT: int(
                            user_input.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
                        ),
                        CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=user_input.get(CONF_HOST, "") if user_input else "",
                ): str,
                vol.Required(
                    CONF_PORT,
                    default=user_input.get(CONF_PORT, DEFAULT_PORT)
                    if user_input
                    else DEFAULT_PORT,
                ): int,
                vol.Required(
                    CONF_RTSP_PORT,
                    default=user_input.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
                    if user_input
                    else DEFAULT_RTSP_PORT,
                ): int,
                vol.Required(
                    CONF_USERNAME,
                    default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
                    if user_input
                    else DEFAULT_USERNAME,
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow reconfiguring IP, ports, or password of an existing camera via UI."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_connection(user_input)
            except DahuaAuthError:
                errors["base"] = "invalid_auth"
            except (DahuaConnectionError, DahuaH5AError, TimeoutError, OSError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during camera reconfiguration")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"{info.machine_name} ({user_input[CONF_HOST].strip()})",
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST].strip(),
                        CONF_PORT: int(user_input.get(CONF_PORT, DEFAULT_PORT)),
                        CONF_RTSP_PORT: int(
                            user_input.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
                        ),
                        CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=entry.data.get(CONF_HOST, "")
                ): str,
                vol.Required(
                    CONF_PORT, default=entry.data.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Required(
                    CONF_RTSP_PORT,
                    default=entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
                ): int,
                vol.Required(
                    CONF_USERNAME,
                    default=entry.data.get(CONF_USERNAME, DEFAULT_USERNAME),
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )


class DahuaH5AOptionsFlow(OptionsFlow):
    """Handle options for a configured Dahua H5A camera."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_subtype = self.config_entry.options.get(
            CONF_STREAM_SUBTYPE, DEFAULT_STREAM_SUBTYPE
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Required(
                        CONF_STREAM_SUBTYPE, default=current_subtype
                    ): vol.In({0: "Main Stream (5MP H.265)", 1: "Sub Stream (SD)"}),
                }
            ),
        )
