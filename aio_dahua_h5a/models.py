"""Data models for Dahua H5A camera state, PTZ, storage, and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DeviceInfo:
    """Hardware and firmware metadata for the Dahua H5A camera."""

    device_type: str = "H5A"
    hardware_version: str = ""
    software_version: str = ""
    build_date: str = ""
    serial_number: str = ""
    machine_name: str = ""
    vendor: str = "Dahua"
    onvif_version: str = ""
    algorithm_version: str = ""


@dataclass(slots=True)
class PtzPreset:
    """Single PTZ preset entry configured on the camera."""

    index: int
    name: str
    position: list[float] = field(default_factory=list)


@dataclass(slots=True)
class PtzStatus:
    """Current PTZ pan/tilt/zoom position and movement state."""

    pan: float = 0.0
    tilt: float = 0.0
    zoom: float = 0.0
    move_status: str = "Idle"
    pan_tilt_status: str = "Idle"
    action: str = "Unknown"
    preset_id: int = 0


@dataclass(slots=True)
class StorageInfo:
    """MicroSD storage status and capacity."""

    present: bool = False
    path: str = ""
    state: str = "None"
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    is_error: bool = False
    health_type: int = 0
    life_percent: float = 100.0

    @property
    def used_percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round((self.used_bytes / self.total_bytes) * 100.0, 2)


@dataclass(slots=True)
class CameraEvent:
    """Real-time event notification emitted by eventManager."""

    code: str
    action: str
    index: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CameraState:
    """Complete snapshot of all controllable states on the Dahua H5A."""

    # Privacy Mode (AELensMask)
    privacy_mode: bool = False
    # Smart Motion & AI Detection (SmartMotionDetect)
    smart_motion_enabled: bool = False
    human_detection: bool = False
    pet_detection: bool = False
    smart_track: bool = False
    smart_sensitivity: str = "Middle"
    # Classic Motion Detection (MotionDetect)
    motion_detection: bool = False
    # Abnormal Sound / Baby Cry Detection (AudioDetect)
    audio_detection: bool = False
    audio_anomaly_enabled: bool = False
    audio_anomaly_sensitivity: int = 50
    # Indicator LED (LightGlobal)
    status_led: bool = True
    # Night Vision (Lighting + VideoInDayNight)
    ir_mode: str = "Auto"  # Auto, Manual, Off
    day_night_mode: str = "Brightness"  # Brightness (Auto), Color (Day), BlackWhite (Night)
    # Image Orientation (VideoInOptions / VideoImageControl)
    mirror: bool = False
    flip: bool = False
    rotate_90: int = 0
    # Audio Volumes & Stream Audio
    mic_volume: int = 50
    speaker_volume: int = 50
    audio_denoise: bool = False
    stream_audio_enabled: bool = True
    # Siren / Speaker Status
    siren_active: bool = False
    white_light_active: bool = False
    alarm_sound_duration: int = 10
    alarm_sound_volume: int = 100
    # Active Alarm / Event flags (live query via eventManager.getEventIndexes)
    motion_active: bool = False
    human_active: bool = False
    pet_active: bool = False
    audio_alarm_active: bool = False
    video_blind_active: bool = False
    # PTZ & Storage
    ptz: PtzStatus = field(default_factory=PtzStatus)
    presets: list[PtzPreset] = field(default_factory=list)
    storage: StorageInfo = field(default_factory=StorageInfo)
