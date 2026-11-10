"""Constants for the Dahua H5A (Local NetSDK) Home Assistant integration."""

from __future__ import annotations

DOMAIN = "dahua_h5a"

DEFAULT_PORT = 37777
DEFAULT_RTSP_PORT = 554
DEFAULT_USERNAME = "admin"
DEFAULT_CHANNEL = 0
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_STREAM_SUBTYPE = 0

CONF_RTSP_PORT = "rtsp_port"
CONF_CHANNEL = "channel"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_STREAM_SUBTYPE = "stream_subtype"

SERVICE_PTZ_MOVE = "ptz_move"
SERVICE_PTZ_GOTO_PRESET = "ptz_goto_preset"
SERVICE_PTZ_SET_PRESET = "ptz_set_preset"
SERVICE_PTZ_REMOVE_PRESET = "ptz_remove_preset"
SERVICE_TRIGGER_SIREN = "trigger_siren"
