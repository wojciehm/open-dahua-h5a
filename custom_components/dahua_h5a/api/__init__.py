"""Clean-room async Python client and CLI for Dahua H5A 5MP 360° cameras."""

from .client import DahuaH5AClient
from .exceptions import (
    DahuaAuthError,
    DahuaConnectionError,
    DahuaH5AError,
    DahuaRpcError,
)
from .models import (
    CameraEvent,
    CameraState,
    DeviceInfo,
    PtzPreset,
    PtzStatus,
    StorageInfo,
)
from .protocol import (
    DahuaNetSdkProtocolClient,
    build_f6_rpc_packet,
    build_step1_challenge_packet,
    build_step2_login_packet,
    compute_dvr2_digest,
    dh_superencipherment,
    md5_hex_upper,
    parse_step1_challenge_response,
)

__all__ = [
    "CameraEvent",
    "CameraState",
    "DahuaAuthError",
    "DahuaConnectionError",
    "DahuaH5AClient",
    "DahuaH5AError",
    "DahuaNetSdkProtocolClient",
    "DahuaRpcError",
    "DeviceInfo",
    "PtzPreset",
    "PtzStatus",
    "StorageInfo",
    "build_f6_rpc_packet",
    "build_step1_challenge_packet",
    "build_step2_login_packet",
    "compute_dvr2_digest",
    "dh_superencipherment",
    "md5_hex_upper",
    "parse_step1_challenge_response",
]

__version__ = "0.1.0"
