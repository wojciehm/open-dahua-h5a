"""Unit tests for high-level DahuaH5AClient methods."""

from __future__ import annotations

from typing import Any
import pytest

from aio_dahua_h5a.client import DahuaH5AClient


class FakeProtocol:
    """In-memory fake protocol recording RPC calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, int | None]] = []
        self.configs: dict[str, Any] = {
            "General": {"MachineName": "Sypialnia"},
            "AELensMask": [{"Enable": True, "Status": False}],
            "SmartMotionDetect": [
                {
                    "Enable": True,
                    "ObjectTypes": {"Human": True, "Animal": False},
                    "SmartTrack": False,
                    "Sensitivity": "Middle",
                }
            ],
            "MotionDetect": [{"Enable": True}],
            "AudioDetect": [
                {"Enable": True, "AnomalyDetect": True, "AnomalySensitive": 50}
            ],
            "LightGlobal": [{"Enable": True}],
            "Lighting": [[{"Mode": "Auto", "Correction": 50, "Sensitive": 3}]],
            "VideoInDayNight": [[{"Mode": "Brightness", "Delay": 2, "Sensitivity": 2}]],
            "VideoInOptions": [
                {"Mirror": False, "Flip": False, "NightOptions": {"Mirror": False, "Flip": False}}
            ],
            "VideoImageControl": [{"Mirror": False, "Flip": False, "Rotate90": 0}],
            "AudioInputVolume": [85],
            "AudioOutputVolume": [80],
            "AudioInDenoise": [{"enable": False}],
            "Encode": [
                {
                    "MainFormat": [{"AudioEnable": True}],
                    "ExtraFormat": [{"AudioEnable": True}],
                }
            ],
            "Sound": {
                "AlarmSound": "/usr/data/audiofiles/siren/alarm.wav",
                "AlarmSoundDuration": 10,
                "AlarmSoundVolume": 100,
            },
        }

    async def connect(self) -> int:
        return 1001

    async def close(self) -> None:
        return None

    async def rpc(
        self,
        method: str,
        params: Any = None,
        *,
        object_id: int | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        self.calls.append((method, params, object_id))
        if method == "configManager.getConfig":
            name = params["name"]
            return {"result": True, "params": {"table": self.configs.get(name)}}
        if method == "configManager.setConfig":
            name = params["name"]
            self.configs[name] = params["table"]
            return {"result": True, "params": {}}
        if method == "ptz.factory.instance":
            return {"result": 2, "params": None}
        if method == "speak.factory.instance":
            return {"result": 3, "params": None}
        if method == "ptz.getStatus":
            return {
                "result": True,
                "params": {
                    "status": {
                        "Postion": [12.5, 4.0, 1.0],
                        "MoveStatus": "Idle",
                        "PanTiltStatus": "Idle",
                        "Action": "Unknown",
                        "PresetID": 1,
                    }
                },
            }
        if method == "ptz.getPresets":
            return {
                "result": True,
                "params": {"presets": [{"Index": 1, "Name": "Sypialnia", "Position": [0, 0, 0]}]},
            }
        if method == "CoaxialControlIO.getStatus":
            return {"result": True, "params": {"status": {"Speaker": "Off", "WhiteLight": "Off"}}}
        if method == "speak.getStatus":
            return {"result": True, "params": {"Info": {"Status": 0, "PlayTimeLeft": 0}}}
        if method == "storage.getDeviceAllInfo":
            return {
                "result": True,
                "params": {
                    "info": [
                        {
                            "State": "Normal",
                            "Detail": [
                                {
                                    "Path": "/mnt/sd",
                                    "TotalBytes": 62534975488.0,
                                    "UsedBytes": 57407406080.0,
                                    "FreeBytes": 5127569408.0,
                                    "IsError": False,
                                    "HealthDataFlag": 1,
                                    "LifePercent": 96.0,
                                }
                            ],
                        }
                    ]
                },
            }
        if method == "eventManager.getEventIndexes":
            code = params["code"]
            return {
                "result": True,
                "params": {"indexes": [0]} if code == "SmartMotionHuman" else {},
            }
        return {"result": True, "params": {}}


@pytest.mark.asyncio
async def test_client_controls_and_full_state() -> None:
    """Verify privacy mask, AI toggles, night vision, PTZ, and full state aggregation."""
    client = DahuaH5AClient("192.0.2.10", "admin", "test_only_pass")
    fake = FakeProtocol()
    client.protocol = fake  # type: ignore[assignment]

    # Privacy Mode
    assert await client.get_privacy_mode() is False
    await client.set_privacy_mode(True)
    assert await client.get_privacy_mode() is True

    # Smart Motion & Pet Detection & Smart Track
    await client.set_pet_detection(True)
    await client.set_smart_track(True)
    await client.set_smart_sensitivity("High")
    scfg = await client.get_smart_motion_config()
    assert scfg["ObjectTypes"]["Animal"] is True
    assert scfg["SmartTrack"] is True
    assert scfg["Sensitivity"] == "High"

    # Night vision presets
    await client.set_night_vision("night")
    nv = await client.get_night_vision()
    assert nv == {"ir_mode": "Manual", "day_night_mode": "BlackWhite"}

    # PTZ step & preset
    await client.ptz_step("left", speed=5, duration=0.05)
    await client.ptz_goto_preset(1)

    # Full state aggregation
    state = await client.get_full_state()
    assert state.privacy_mode is True
    assert state.pet_detection is True
    assert state.smart_track is True
    assert state.human_active is True
    assert state.motion_active is False
    assert state.ptz.pan == 12.5
    assert len(state.presets) == 1
    assert state.presets[0].name == "Sypialnia"
    assert state.storage.present is True
    assert state.storage.used_percent == 91.8
