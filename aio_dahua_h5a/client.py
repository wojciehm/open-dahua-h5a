"""High-level async client for full local control of the Dahua H5A camera."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .exceptions import DahuaH5AError, DahuaRpcError
from .models import (
    CameraEvent,
    CameraState,
    DeviceInfo,
    PtzPreset,
    PtzStatus,
    StorageInfo,
)
from .protocol import DahuaNetSdkProtocolClient

PTZ_DIRECTION_MAP: dict[str, str] = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "left_up": "LeftUp",
    "leftup": "LeftUp",
    "right_up": "RightUp",
    "rightup": "RightUp",
    "left_down": "LeftDown",
    "leftdown": "LeftDown",
    "right_down": "RightDown",
    "rightdown": "RightDown",
}


class DahuaH5AClient:
    """High-level async controller for the Dahua H5A 5MP 360° indoor camera."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        port: int = 37777,
        rtsp_port: int = 554,
        timeout: float = 8.0,
    ) -> None:
        self.host = host
        self.port = port
        self.rtsp_port = rtsp_port
        self.username = username
        self.password = password
        self.protocol = DahuaNetSdkProtocolClient(
            host=host,
            username=username,
            password=password,
            port=port,
            timeout=timeout,
        )
        self._ptz_object_id: int | None = None
        self._speak_object_id: int | None = None

    async def __aenter__(self) -> DahuaH5AClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def connect(self) -> int:
        """Connect and authenticate over Port 37777."""
        self._ptz_object_id = None
        self._speak_object_id = None
        return await self.protocol.connect()

    async def close(self) -> None:
        """Close the Port 37777 session."""
        self._ptz_object_id = None
        self._speak_object_id = None
        await self.protocol.close()

    def register_event_callback(
        self, callback: Callable[[CameraEvent], Any]
    ) -> Callable[[], None]:
        """Register a listener for real-time `client.notifyEventStream` events."""
        return self.protocol.register_event_callback(callback)

    async def attach_events(self, codes: list[str] | None = None) -> int:
        """Subscribe to real-time camera events (`VideoMotion`, `SmartMotionHuman`, etc.)."""
        return await self.protocol.attach_events(codes)

    async def rpc(
        self,
        method: str,
        params: Any = None,
        *,
        object_id: int | None = None,
        raise_on_error: bool = False,
    ) -> dict[str, Any]:
        """Execute a raw `0xf6` JSON-RPC request."""
        return await self.protocol.rpc(
            method,
            params,
            object_id=object_id,
            raise_on_error=raise_on_error,
        )

    async def get_config(self, name: str) -> Any:
        """Fetch a configuration table via `configManager.getConfig`."""
        resp = await self.rpc(
            "configManager.getConfig",
            {"name": name},
            raise_on_error=True,
        )
        return (resp.get("params") or {}).get("table")

    async def set_config(
        self,
        name: str,
        table: Any,
        options: list[str] | None = None,
    ) -> bool:
        """Write a configuration table via `configManager.setConfig`."""
        resp = await self.rpc(
            "configManager.setConfig",
            {"name": name, "table": table, "options": options or []},
            raise_on_error=True,
        )
        return bool(resp.get("result"))

    # -------------------------------------------------------------------------
    # Device Metadata & Introspection
    # -------------------------------------------------------------------------

    async def get_device_info(self) -> DeviceInfo:
        """Query hardware, firmware, serial, and machine name metadata."""
        dev_type_r = await self.rpc("magicBox.getDeviceType")
        hw_r = await self.rpc("magicBox.getHardwareVersion")
        sw_r = await self.rpc("magicBox.getSoftwareVersion")
        sn_r = await self.rpc("magicBox.getSerialNo")
        vendor_r = await self.rpc("magicBox.getVendor")
        general_cfg = await self.get_config("General")

        sw_info = (sw_r.get("params") or {}).get("version") or {}
        machine_name = ""
        if isinstance(general_cfg, dict):
            machine_name = str(general_cfg.get("MachineName", ""))

        return DeviceInfo(
            device_type=str((dev_type_r.get("params") or {}).get("type", "H5A")),
            hardware_version=str((hw_r.get("params") or {}).get("version", "")),
            software_version=str(sw_info.get("Version", "")),
            build_date=str(sw_info.get("BuildDate", "")),
            serial_number=str((sn_r.get("params") or {}).get("sn", "")),
            machine_name=machine_name,
            vendor=str((vendor_r.get("params") or {}).get("vendor", "Dahua")),
            onvif_version=str(sw_info.get("OnvifVersion", "")),
            algorithm_version=str(sw_info.get("AlgorithmVersion", "")),
        )

    async def get_member_names(self) -> list[str]:
        """Return all configuration table names supported by the camera."""
        resp = await self.rpc("configManager.getMemberNames", raise_on_error=True)
        names = (resp.get("params") or {}).get("names") or []
        return [str(n) for n in names]

    async def list_component_methods(self, component: str) -> list[str]:
        """List all RPC methods exposed by a given component (e.g., `ptz`, `magicBox`)."""
        resp = await self.rpc(f"{component}.listMethod", raise_on_error=True)
        methods = (resp.get("params") or {}).get("method") or []
        return [str(m) for m in methods]

    # -------------------------------------------------------------------------
    # 1. Privacy Mode (Lens Mask — AELensMask)
    # -------------------------------------------------------------------------

    async def get_privacy_mode(self) -> bool:
        """Return True when the physical lens privacy mask is active (closed)."""
        table = await self.get_config("AELensMask")
        if isinstance(table, list) and table:
            return bool(table[0].get("Status", False))
        return False

    async def set_privacy_mode(self, enabled: bool) -> bool:
        """Enable (`True` = hide lens) or disable (`False` = open lens) Privacy Mode."""
        table = await self.get_config("AELensMask")
        if not isinstance(table, list) or not table:
            table = [{"Enable": True, "Status": bool(enabled)}]
        else:
            table[0]["Enable"] = True
            table[0]["Status"] = bool(enabled)
        return await self.set_config("AELensMask", table)

    # -------------------------------------------------------------------------
    # 2. AI Smart Motion Detection & Auto-Tracking (SmartMotionDetect)
    # -------------------------------------------------------------------------

    async def get_smart_motion_config(self) -> dict[str, Any]:
        """Fetch the `SmartMotionDetect` configuration dictionary for channel 0."""
        table = await self.get_config("SmartMotionDetect")
        if isinstance(table, list) and table and isinstance(table[0], dict):
            return table[0]
        return {}

    async def set_smart_motion(
        self,
        *,
        enabled: bool | None = None,
        human: bool | None = None,
        pet: bool | None = None,
        smart_track: bool | None = None,
        sensitivity: str | None = None,
    ) -> bool:
        """Update AI Smart Motion Detection, Human/Pet filters, and Auto-Tracking."""
        table = await self.get_config("SmartMotionDetect")
        if not isinstance(table, list) or not table:
            raise DahuaH5AError("SmartMotionDetect table is empty or unavailable")

        cfg = table[0]
        if enabled is not None:
            cfg["Enable"] = bool(enabled)
        obj_types = cfg.setdefault("ObjectTypes", {})
        if human is not None:
            obj_types["Human"] = bool(human)
            if human:
                cfg["Enable"] = True
        if pet is not None:
            obj_types["Animal"] = bool(pet)
            if pet:
                cfg["Enable"] = True
        if smart_track is not None:
            cfg["SmartTrack"] = bool(smart_track)
        if sensitivity is not None:
            norm = sensitivity.strip().capitalize()
            if norm in ("Mid", "Medium"):
                norm = "Middle"
            if norm not in ("Low", "Middle", "High"):
                raise ValueError(
                    f"Invalid sensitivity '{sensitivity}'. Must be Low, Middle, or High."
                )
            cfg["Sensitivity"] = norm

        return await self.set_config("SmartMotionDetect", table)

    async def set_human_detection(self, enabled: bool) -> bool:
        """Enable or disable AI Human Detection."""
        return await self.set_smart_motion(human=enabled)

    async def set_pet_detection(self, enabled: bool) -> bool:
        """Enable or disable AI Pet/Animal Detection."""
        return await self.set_smart_motion(pet=enabled)

    async def set_smart_track(self, enabled: bool) -> bool:
        """Enable or disable Smart Auto-Tracking."""
        return await self.set_smart_motion(smart_track=enabled)

    async def set_smart_sensitivity(self, sensitivity: str) -> bool:
        """Set Smart Motion sensitivity (`Low`, `Middle`, `High`)."""
        return await self.set_smart_motion(sensitivity=sensitivity)

    # -------------------------------------------------------------------------
    # 3. Classic Motion Detection (MotionDetect)
    # -------------------------------------------------------------------------

    async def get_motion_detection(self) -> bool:
        """Return True if classic Motion Detection is enabled on channel 0."""
        table = await self.get_config("MotionDetect")
        if isinstance(table, list) and table:
            return bool(table[0].get("Enable", False))
        return False

    async def set_motion_detection(self, enabled: bool) -> bool:
        """Enable or disable classic Motion Detection on channel 0."""
        table = await self.get_config("MotionDetect")
        if not isinstance(table, list) or not table:
            raise DahuaH5AError("MotionDetect table is empty or unavailable")
        table[0]["Enable"] = bool(enabled)
        return await self.set_config("MotionDetect", table)

    # -------------------------------------------------------------------------
    # 4. Abnormal Sound / Baby Cry Detection (AudioDetect)
    # -------------------------------------------------------------------------

    async def get_audio_detection(self) -> dict[str, Any]:
        """Return `AudioDetect` configuration for channel 0."""
        table = await self.get_config("AudioDetect")
        if isinstance(table, list) and table and isinstance(table[0], dict):
            return table[0]
        return {}

    async def set_audio_detection(
        self,
        *,
        enabled: bool | None = None,
        anomaly_enabled: bool | None = None,
        sensitivity: int | None = None,
    ) -> bool:
        """Update Abnormal Sound / Baby Cry detection and sensitivity (1..100)."""
        table = await self.get_config("AudioDetect")
        if not isinstance(table, list) or not table:
            raise DahuaH5AError("AudioDetect table is empty or unavailable")
        cfg = table[0]
        if enabled is not None:
            cfg["Enable"] = bool(enabled)
            if anomaly_enabled is None:
                cfg["AnomalyDetect"] = bool(enabled)
        if anomaly_enabled is not None:
            cfg["AnomalyDetect"] = bool(anomaly_enabled)
        if sensitivity is not None:
            val = max(1, min(100, int(sensitivity)))
            cfg["AnomalySensitive"] = val
        return await self.set_config("AudioDetect", table)

    # -------------------------------------------------------------------------
    # 5. Status Indicator LED (LightGlobal)
    # -------------------------------------------------------------------------

    async def get_status_led(self) -> bool:
        """Return True if the front status indicator LED is enabled."""
        table = await self.get_config("LightGlobal")
        if isinstance(table, list) and table:
            return bool(table[0].get("Enable", False))
        return False

    async def set_status_led(self, enabled: bool) -> bool:
        """Turn the front status indicator LED on (`True`) or off (`False`)."""
        table = await self.get_config("LightGlobal")
        if not isinstance(table, list) or not table:
            table = [{"Enable": bool(enabled)}]
        else:
            table[0]["Enable"] = bool(enabled)
        return await self.set_config("LightGlobal", table)

    # -------------------------------------------------------------------------
    # 6. Night Vision & Day/Night Mode (Lighting + VideoInDayNight)
    # -------------------------------------------------------------------------

    async def get_night_vision(self) -> dict[str, str]:
        """Return current IR illuminator mode (`Auto`/`Manual`/`Off`) and Day/Night mode."""
        lighting = await self.get_config("Lighting")
        day_night = await self.get_config("VideoInDayNight")
        ir_mode = "Auto"
        if isinstance(lighting, list) and lighting and isinstance(lighting[0], list) and lighting[0]:
            ir_mode = str(lighting[0][0].get("Mode", "Auto"))
        dn_mode = "Brightness"
        if isinstance(day_night, list) and day_night and isinstance(day_night[0], list) and day_night[0]:
            dn_mode = str(day_night[0][0].get("Mode", "Brightness"))
        return {"ir_mode": ir_mode, "day_night_mode": dn_mode}

    async def set_ir_mode(self, mode: str) -> bool:
        """Set IR illuminator mode (`Auto`, `Manual`, or `Off`)."""
        norm_map = {"auto": "Auto", "manual": "Manual", "on": "Manual", "off": "Off"}
        norm = norm_map.get(mode.strip().lower(), mode)
        if norm not in ("Auto", "Manual", "Off"):
            raise ValueError(f"Invalid IR mode '{mode}'. Must be Auto, Manual, or Off.")
        table = await self.get_config("Lighting")
        if isinstance(table, list) and table and isinstance(table[0], list):
            for entry in table[0]:
                if isinstance(entry, dict):
                    entry["Mode"] = norm
        return await self.set_config("Lighting", table)

    async def set_day_night_mode(self, mode: str) -> bool:
        """Set ICR Day/Night switch mode (`Brightness` = Auto, `Color` = Day, `BlackWhite` = Night)."""
        norm_map = {
            "auto": "Brightness",
            "brightness": "Brightness",
            "color": "Color",
            "day": "Color",
            "blackwhite": "BlackWhite",
            "bw": "BlackWhite",
            "night": "BlackWhite",
        }
        norm = norm_map.get(mode.strip().lower(), mode)
        if norm not in ("Brightness", "Color", "BlackWhite"):
            raise ValueError(
                f"Invalid day/night mode '{mode}'. Must be Brightness, Color, or BlackWhite."
            )
        table = await self.get_config("VideoInDayNight")
        if isinstance(table, list) and table and isinstance(table[0], list):
            for entry in table[0]:
                if isinstance(entry, dict):
                    entry["Mode"] = norm
        return await self.set_config("VideoInDayNight", table)

    async def set_night_vision(self, preset: str) -> bool:
        """Set both IR illuminator and Day/Night mode (`auto`, `night`, `day`)."""
        key = preset.strip().lower()
        if key == "auto":
            r1 = await self.set_ir_mode("Auto")
            r2 = await self.set_day_night_mode("Brightness")
            return r1 and r2
        if key in ("night", "ir", "on", "blackwhite", "bw"):
            r1 = await self.set_ir_mode("Manual")
            r2 = await self.set_day_night_mode("BlackWhite")
            return r1 and r2
        if key in ("day", "off", "color"):
            r1 = await self.set_ir_mode("Off")
            r2 = await self.set_day_night_mode("Color")
            return r1 and r2
        raise ValueError(
            f"Invalid night vision preset '{preset}'. Expected auto, night, or day."
        )

    # -------------------------------------------------------------------------
    # 7. Image Orientation (Mirror / Flip / Rotate90)
    # -------------------------------------------------------------------------

    async def get_image_orientation(self) -> dict[str, Any]:
        """Return `mirror`, `flip`, and `rotate_90` settings."""
        opts = await self.get_config("VideoInOptions")
        img_ctrl = await self.get_config("VideoImageControl")
        mirror = False
        flip = False
        rotate_90 = 0
        if isinstance(opts, list) and opts:
            mirror = bool(opts[0].get("Mirror", False))
            flip = bool(opts[0].get("Flip", False))
        if isinstance(img_ctrl, list) and img_ctrl:
            rotate_90 = int(img_ctrl[0].get("Rotate90", 0))
        return {"mirror": mirror, "flip": flip, "rotate_90": rotate_90}

    async def set_mirror_flip(
        self,
        *,
        mirror: bool | None = None,
        flip: bool | None = None,
        rotate_90: int | None = None,
    ) -> bool:
        """Set image horizontal mirror, vertical 180° flip, and/or 90° rotation."""
        ok = True
        if mirror is not None or flip is not None:
            opts = await self.get_config("VideoInOptions")
            if isinstance(opts, list) and opts:
                if mirror is not None:
                    opts[0]["Mirror"] = bool(mirror)
                if flip is not None:
                    opts[0]["Flip"] = bool(flip)
                    if isinstance(opts[0].get("NightOptions"), dict):
                        opts[0]["NightOptions"]["Flip"] = bool(flip)
                        if mirror is not None:
                            opts[0]["NightOptions"]["Mirror"] = bool(mirror)
                ok = await self.set_config("VideoInOptions", opts) and ok

        img_ctrl = await self.get_config("VideoImageControl")
        if isinstance(img_ctrl, list) and img_ctrl:
            if mirror is not None:
                img_ctrl[0]["Mirror"] = bool(mirror)
            if flip is not None:
                img_ctrl[0]["Flip"] = bool(flip)
            if rotate_90 is not None:
                img_ctrl[0]["Rotate90"] = int(rotate_90)
            ok = await self.set_config("VideoImageControl", img_ctrl) and ok
        return ok

    # -------------------------------------------------------------------------
    # 8. Microphone, Speaker Volume, Denoise & Stream Audio
    # -------------------------------------------------------------------------

    async def get_mic_volume(self) -> int:
        """Return microphone input volume (`0..100`)."""
        table = await self.get_config("AudioInputVolume")
        if isinstance(table, list) and table:
            return int(table[0])
        return 50

    async def set_mic_volume(self, volume: int) -> bool:
        """Set microphone input volume (`0..100`)."""
        val = max(0, min(100, int(volume)))
        return await self.set_config("AudioInputVolume", [val])

    async def get_speaker_volume(self) -> int:
        """Return speaker output volume (`0..100`)."""
        table = await self.get_config("AudioOutputVolume")
        if isinstance(table, list) and table:
            return int(table[0])
        return 50

    async def set_speaker_volume(self, volume: int) -> bool:
        """Set speaker output volume (`0..100`)."""
        val = max(0, min(100, int(volume)))
        return await self.set_config("AudioOutputVolume", [val])

    async def get_audio_denoise(self) -> bool:
        """Return True if microphone noise reduction (`AudioInDenoise`) is enabled."""
        table = await self.get_config("AudioInDenoise")
        if isinstance(table, list) and table:
            return bool(table[0].get("enable", False))
        return False

    async def set_audio_denoise(self, enabled: bool) -> bool:
        """Enable or disable microphone noise reduction (`AudioInDenoise`)."""
        table = await self.get_config("AudioInDenoise")
        if not isinstance(table, list) or not table:
            table = [{"enable": bool(enabled)}]
        else:
            table[0]["enable"] = bool(enabled)
        return await self.set_config("AudioInDenoise", table)

    async def get_stream_audio(self) -> bool:
        """Return True if audio is enabled on the main video stream (`Encode`)."""
        table = await self.get_config("Encode")
        if isinstance(table, list) and table:
            main_fmt = table[0].get("MainFormat") or []
            if main_fmt and isinstance(main_fmt[0], dict):
                return bool(main_fmt[0].get("AudioEnable", True))
        return True

    async def set_stream_audio(self, enabled: bool) -> bool:
        """Enable or disable audio encoding in both MainFormat and ExtraFormat streams."""
        table = await self.get_config("Encode")
        if not isinstance(table, list) or not table:
            raise DahuaH5AError("Encode table is empty or unavailable")
        for fmt_key in ("MainFormat", "ExtraFormat"):
            for stream in table[0].get(fmt_key) or []:
                if isinstance(stream, dict) and "AudioEnable" in stream:
                    stream["AudioEnable"] = bool(enabled)
        return await self.set_config("Encode", table)

    # -------------------------------------------------------------------------
    # 9. Siren / Audio Alarm Control (Sound + CoaxialControlIO + speak)
    # -------------------------------------------------------------------------

    async def _get_speak_object(self) -> int:
        if self._speak_object_id is not None:
            return self._speak_object_id
        resp = await self.rpc(
            "speak.factory.instance", {"channel": 0}, raise_on_error=True
        )
        obj_id = int(resp.get("result", 0))
        self._speak_object_id = obj_id
        return obj_id

    async def get_siren_status(self) -> dict[str, Any]:
        """Return current siren/speaker status and `Sound` configuration."""
        coax = await self.rpc("CoaxialControlIO.getStatus", {"channel": 0})
        coax_status = (coax.get("params") or {}).get("status") or {}
        sound_cfg = await self.get_config("Sound")
        spk_obj = await self._get_speak_object()
        spk_resp = await self.rpc("speak.getStatus", None, object_id=spk_obj)
        spk_info = ((spk_resp.get("params") or {}).get("Info")) or {}

        speaker_on = (
            str(coax_status.get("Speaker", "Off")).lower() == "on"
            or int(spk_info.get("Status", 0)) != 0
        )
        white_light_on = str(coax_status.get("WhiteLight", "Off")).lower() == "on"
        duration = 10
        volume = 100
        alarm_file = "/usr/data/audiofiles/siren/alarm.wav"
        if isinstance(sound_cfg, dict):
            duration = int(sound_cfg.get("AlarmSoundDuration", 10))
            volume = int(sound_cfg.get("AlarmSoundVolume", 100))
            alarm_file = str(sound_cfg.get("AlarmSound", alarm_file))

        return {
            "siren_active": speaker_on,
            "white_light_active": white_light_on,
            "play_time_left": int(spk_info.get("PlayTimeLeft", 0)),
            "alarm_sound": alarm_file,
            "alarm_sound_duration": duration,
            "alarm_sound_volume": volume,
        }

    async def set_siren_config(
        self,
        *,
        duration: int | None = None,
        volume: int | None = None,
    ) -> bool:
        """Update siren alarm duration (`1..300` s) and volume (`0..100`)."""
        sound_cfg = await self.get_config("Sound")
        if not isinstance(sound_cfg, dict):
            sound_cfg = {
                "AlarmSound": "/usr/data/audiofiles/siren/alarm.wav",
                "AlarmSoundDuration": 10,
                "AlarmSoundVolume": 100,
            }
        if duration is not None:
            sound_cfg["AlarmSoundDuration"] = max(1, min(300, int(duration)))
        if volume is not None:
            sound_cfg["AlarmSoundVolume"] = max(0, min(100, int(volume)))
        return await self.set_config("Sound", sound_cfg)

    async def trigger_siren(self, active: bool = True) -> bool:
        """Trigger or stop the built-in camera siren (`/usr/data/audiofiles/siren/alarm.wav`)."""
        # 1. Try CoaxialControlIO.control
        coax_res = await self.rpc(
            "CoaxialControlIO.control",
            {
                "channel": 0,
                "info": [
                    {
                        "Type": "Speaker",
                        "IO": "On" if active else "Off",
                        "TriggerMode": "Manual",
                    }
                ],
            },
        )
        # 2. Also invoke speak.startPlay / speak.stopPlay on the audio file
        spk_obj = await self._get_speak_object()
        if active:
            sound_cfg = await self.get_config("Sound")
            alarm_path = "/usr/data/audiofiles/siren/alarm.wav"
            if isinstance(sound_cfg, dict) and sound_cfg.get("AlarmSound"):
                alarm_path = str(sound_cfg["AlarmSound"])
            spk_res = await self.rpc(
                "speak.startPlay",
                {"path": alarm_path, "Speaker": True},
                object_id=spk_obj,
            )
        else:
            spk_res = await self.rpc(
                "speak.stopPlay",
                {"Speaker": True},
                object_id=spk_obj,
            )
        return bool(coax_res.get("result") or spk_res.get("result"))

    # -------------------------------------------------------------------------
    # 10. PTZ Control (ptz.factory.instance -> object_id)
    # -------------------------------------------------------------------------

    async def _get_ptz_object(self) -> int:
        if self._ptz_object_id is not None:
            return self._ptz_object_id
        resp = await self.rpc(
            "ptz.factory.instance", {"channel": 0}, raise_on_error=True
        )
        obj_id = int(resp.get("result", 0))
        if obj_id == 0:
            raise DahuaRpcError("ptz.factory.instance", "Invalid PTZ object handle", resp)
        self._ptz_object_id = obj_id
        return obj_id

    async def ptz_status(self) -> PtzStatus:
        """Get current PTZ pan/tilt/zoom coordinates and movement status."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc("ptz.getStatus", None, object_id=obj_id, raise_on_error=True)
        st = (resp.get("params") or {}).get("status") or {}
        pos = st.get("Postion") or st.get("Position") or [0.0, 0.0, 0.0]
        pan = float(pos[0]) if len(pos) > 0 else 0.0
        tilt = float(pos[1]) if len(pos) > 1 else 0.0
        zoom = float(pos[2]) if len(pos) > 2 else 0.0
        return PtzStatus(
            pan=pan,
            tilt=tilt,
            zoom=zoom,
            move_status=str(st.get("MoveStatus", "Idle")),
            pan_tilt_status=str(st.get("PanTiltStatus", "Idle")),
            action=str(st.get("Action", "Unknown")),
            preset_id=int(st.get("PresetID", 0)),
        )

    async def ptz_start(
        self,
        direction: str,
        speed: int = 4,
        arg1: int | None = None,
        arg2: int | None = None,
        arg3: int = 0,
    ) -> bool:
        """Start continuous PTZ movement in `direction` (`Up`, `Down`, `Left`, `Right`, etc.)."""
        code = PTZ_DIRECTION_MAP.get(direction.strip().lower(), direction)
        spd = max(1, min(8, int(speed)))
        a1 = spd if arg1 is None else int(arg1)
        a2 = spd if arg2 is None else int(arg2)
        obj_id = await self._get_ptz_object()
        resp = await self.rpc(
            "ptz.start",
            {"channel": 0, "code": code, "arg1": a1, "arg2": a2, "arg3": arg3},
            object_id=obj_id,
            raise_on_error=True,
        )
        return bool(resp.get("result"))

    async def ptz_stop(self, direction: str = "Up") -> bool:
        """Stop continuous PTZ movement."""
        code = PTZ_DIRECTION_MAP.get(direction.strip().lower(), direction)
        obj_id = await self._get_ptz_object()
        resp = await self.rpc(
            "ptz.stop",
            {"channel": 0, "code": code, "arg1": 0, "arg2": 0, "arg3": 0},
            object_id=obj_id,
            raise_on_error=True,
        )
        return bool(resp.get("result"))

    async def ptz_step(
        self,
        direction: str,
        speed: int = 4,
        duration: float = 0.35,
    ) -> bool:
        """Move PTZ in `direction` for `duration` seconds and stop automatically."""
        await self.ptz_start(direction, speed=speed)
        try:
            await asyncio.sleep(max(0.05, float(duration)))
        finally:
            await self.ptz_stop(direction)
        return True

    async def ptz_get_presets(self) -> list[PtzPreset]:
        """Return all configured PTZ presets on the camera."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc("ptz.getPresets", None, object_id=obj_id, raise_on_error=True)
        raw_list = (resp.get("params") or {}).get("presets") or []
        presets: list[PtzPreset] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            pos = item.get("Position") or []
            presets.append(
                PtzPreset(
                    index=int(item.get("Index", 0)),
                    name=str(item.get("Name", "")),
                    position=[float(x) for x in pos if isinstance(x, (int, float))],
                )
            )
        return presets

    async def ptz_goto_preset(self, index: int) -> bool:
        """Move camera to preset number `index`."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc(
            "ptz.gotoPreset",
            {"index": int(index)},
            object_id=obj_id,
        )
        if resp.get("result"):
            return True
        resp2 = await self.rpc(
            "ptz.start",
            {"code": "GotoPreset", "arg1": int(index), "arg2": 0, "arg3": 0},
            object_id=obj_id,
            raise_on_error=True,
        )
        return bool(resp2.get("result"))

    async def ptz_set_preset(self, index: int, name: str) -> bool:
        """Save the current PTZ position as preset `index` with `name`."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc(
            "ptz.setPreset",
            {"index": int(index), "name": str(name)},
            object_id=obj_id,
            raise_on_error=True,
        )
        return bool(resp.get("result"))

    async def ptz_remove_preset(self, index: int) -> bool:
        """Delete PTZ preset `index`."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc(
            "ptz.removePreset",
            {"index": int(index)},
            object_id=obj_id,
            raise_on_error=True,
        )
        return bool(resp.get("result"))

    async def ptz_restart(self) -> bool:
        """Run PTZ self-calibration / homing (`ptz.restartPtz`)."""
        obj_id = await self._get_ptz_object()
        resp = await self.rpc("ptz.restartPtz", None, object_id=obj_id, raise_on_error=True)
        return bool(resp.get("result"))

    # -------------------------------------------------------------------------
    # 11. Storage & Active Events
    # -------------------------------------------------------------------------

    async def get_storage_info(self) -> StorageInfo:
        """Query MicroSD card presence, capacity, usage, and health."""
        resp = await self.rpc("storage.getDeviceAllInfo")
        info_list = (resp.get("params") or {}).get("info") or []
        if not info_list or not isinstance(info_list[0], dict):
            return StorageInfo(present=False)
        dev = info_list[0]
        details = dev.get("Detail") or []
        det = details[0] if (details and isinstance(details[0], dict)) else {}
        total_b = int(float(det.get("TotalBytes", 0)))
        used_b = int(float(det.get("UsedBytes", 0)))
        free_b = int(float(det.get("FreeBytes", max(0, total_b - used_b))))
        return StorageInfo(
            present=True,
            path=str(det.get("Path", "")),
            state=str(dev.get("State", "Normal")),
            total_bytes=total_b,
            used_bytes=used_b,
            free_bytes=free_b,
            is_error=bool(det.get("IsError", False)),
            health_type=int(det.get("HealthDataFlag", 0)),
            life_percent=float(det.get("LifePercent", 100.0)),
        )

    async def get_active_events(self) -> dict[str, bool]:
        """Poll currently active alarm/detection states via `eventManager.getEventIndexes`."""
        codes = (
            "VideoMotion",
            "SmartMotionHuman",
            "SmartMotionAnimal",
            "AudioMutation",
            "VideoBlind",
        )
        active: dict[str, bool] = {}
        for code in codes:
            resp = await self.rpc("eventManager.getEventIndexes", {"code": code})
            indexes = (resp.get("params") or {}).get("indexes")
            active[code] = bool(isinstance(indexes, list) and len(indexes) > 0)
        return active

    async def get_full_state(self) -> CameraState:
        """Fetch all camera states and settings in a single structured `CameraState`."""
        privacy = await self.get_privacy_mode()
        smart_cfg = await self.get_smart_motion_config()
        motion = await self.get_motion_detection()
        audio_cfg = await self.get_audio_detection()
        led = await self.get_status_led()
        nv = await self.get_night_vision()
        orient = await self.get_image_orientation()
        mic_vol = await self.get_mic_volume()
        spk_vol = await self.get_speaker_volume()
        denoise = await self.get_audio_denoise()
        stream_audio = await self.get_stream_audio()
        siren = await self.get_siren_status()
        active_ev = await self.get_active_events()
        ptz_st = await self.ptz_status()
        presets = await self.ptz_get_presets()
        storage = await self.get_storage_info()

        obj_types = smart_cfg.get("ObjectTypes") or {}
        return CameraState(
            privacy_mode=privacy,
            smart_motion_enabled=bool(smart_cfg.get("Enable", False)),
            human_detection=bool(obj_types.get("Human", False)),
            pet_detection=bool(obj_types.get("Animal", False)),
            smart_track=bool(smart_cfg.get("SmartTrack", False)),
            smart_sensitivity=str(smart_cfg.get("Sensitivity", "Middle")),
            motion_detection=motion,
            audio_detection=bool(audio_cfg.get("Enable", False)),
            audio_anomaly_enabled=bool(audio_cfg.get("AnomalyDetect", False)),
            audio_anomaly_sensitivity=int(audio_cfg.get("AnomalySensitive", 50)),
            status_led=led,
            ir_mode=nv["ir_mode"],
            day_night_mode=nv["day_night_mode"],
            mirror=bool(orient["mirror"]),
            flip=bool(orient["flip"]),
            rotate_90=int(orient["rotate_90"]),
            mic_volume=mic_vol,
            speaker_volume=spk_vol,
            audio_denoise=denoise,
            stream_audio_enabled=stream_audio,
            siren_active=bool(siren["siren_active"]),
            white_light_active=bool(siren["white_light_active"]),
            alarm_sound_duration=int(siren["alarm_sound_duration"]),
            alarm_sound_volume=int(siren["alarm_sound_volume"]),
            motion_active=active_ev.get("VideoMotion", False),
            human_active=active_ev.get("SmartMotionHuman", False),
            pet_active=active_ev.get("SmartMotionAnimal", False),
            audio_alarm_active=active_ev.get("AudioMutation", False),
            video_blind_active=active_ev.get("VideoBlind", False),
            ptz=ptz_st,
            presets=presets,
            storage=storage,
        )

    # -------------------------------------------------------------------------
    # 12. RTSP Video Streams & Snapshot Helper
    # -------------------------------------------------------------------------

    def get_rtsp_url(self, subtype: int = 0, *, redact_password: bool = False) -> str:
        """Build the RTSP stream URL (`subtype=0` for 5MP Main H.265, `subtype=1` for Sub)."""
        user_enc = quote(self.username, safe="")
        pwd_enc = "***" if redact_password else quote(self.password, safe="")
        return (
            f"rtsp://{user_enc}:{pwd_enc}@{self.host}:{self.rtsp_port}"
            f"/cam/realmonitor?channel=1&subtype={int(subtype)}"
        )

    async def capture_snapshot(
        self,
        output_path: str | Path | None = None,
        *,
        subtype: int = 0,
        timeout: float = 12.0,
    ) -> bytes:
        """Capture a single JPEG frame from the RTSP stream using `ffmpeg`."""
        rtsp_url = self.get_rtsp_url(subtype=subtype)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "2",
            "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as err:
            proc.kill()
            raise DahuaH5AError(f"Snapshot capture timed out after {timeout}s") from err

        if proc.returncode != 0 or not stdout:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise DahuaH5AError(f"ffmpeg snapshot failed: {err_msg}")

        if output_path is not None:
            Path(output_path).write_bytes(stdout)
        return stdout

    async def reboot(self) -> bool:
        """Reboot the camera via `magicBox.reboot`."""
        resp = await self.rpc("magicBox.reboot", None, raise_on_error=True)
        return bool(resp.get("result"))
