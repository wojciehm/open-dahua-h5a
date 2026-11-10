# open-dahua-h5a (`aio-dahua-h5a`)

Clean-room, dependency-free **async Python library and CLI (`dahua-h5a`)** for 100% local control of **Dahua H5A 5MP 360° Indoor Wi-Fi 6 (`DH-H5A` / `IPC-H5A`)** cameras over **TCP Port `37777` (NetSDK DVR2 `0xa0` + Embedded JSON-RPC `0xf6`)** and **RTSP Port `554`**.

Reconstructed via static reverse engineering of Dahua's macOS/Windows `ConfigTool` (`libdhnetsdk.so`, `libdhconfigsdk.so`, `dhnetsdk.dll`) and Android `DMSS` (`libnetsdk.so`, `libconfigsdk.so`) without using any proprietary vendor binaries or cloud services.

---

## Why Port `37777` Instead of HTTP Port `80`?

On the consumer/IoT **Dahua H5A (`DH-H5A`)**, firmware `V2.860.0000000.26.R` explicitly disables the legacy HTTP Web UI and `/cgi-bin/*.cgi` API (`"DeviceWebCaps": {"SupportLocalWebSource": false, "SupportWebService": false}`). Port `80` only runs an embedded `gSOAP/2.8` ONVIF endpoint, while **Port `37777`** exposes the complete JSON-RPC control plane encapsulated inside 32-byte DVR2 binary frames (`0xa0` login + `0xf6` JSON-RPC).

See [`docs/PROTOCOL_SPEC.md`](docs/PROTOCOL_SPEC.md) for the full byte-level specification, including the `DH_Superencipherment` Base62 password hash and `0xf6` frame reassembly rules, and [`docs/h5a_capabilities.json`](docs/h5a_capabilities.json) for the complete camera capability and RPC method dump.

---

## Supported Camera Features

| Feature | Port `37777` RPC / Config Table | CLI Subcommand |
| :--- | :--- | :--- |
| **Privacy Mode (Physical Lens Mask)** | `AELensMask` (`Status: true/false`) | `dahua-h5a privacy [on\|off]` |
| **AI Human Detection** | `SmartMotionDetect` (`ObjectTypes.Human`) | `dahua-h5a human-detect [on\|off]` |
| **AI Pet / Animal Detection** | `SmartMotionDetect` (`ObjectTypes.Animal`) | `dahua-h5a pet-detect [on\|off]` |
| **Smart Auto-Tracking (PTZ)** | `SmartMotionDetect` (`SmartTrack`) | `dahua-h5a smart-track [on\|off]` |
| **Motion Detection & Sensitivity** | `MotionDetect` + `SmartMotionDetect` (`Low`/`Middle`/`High`) | `dahua-h5a motion-detect [on\|off] [--sensitivity ...]` |
| **Abnormal Sound / Baby Cry Detection** | `AudioDetect` (`Enable`, `AnomalyDetect`, `AnomalySensitive`) | `dahua-h5a audio-detect [on\|off] [--sensitivity 1..100]` |
| **Front Status Indicator LED** | `LightGlobal` (`Enable`) | `dahua-h5a led [on\|off]` |
| **Night Vision & ICR Filter** | `Lighting` (`Auto`/`Manual`/`Off`) + `VideoInDayNight` (`Brightness`/`Color`/`BlackWhite`) | `dahua-h5a night-vision [auto\|night\|day]` |
| **Image 180° Flip & Horizontal Mirror** | `VideoInOptions` + `VideoImageControl` | `dahua-h5a flip [on\|off]`, `dahua-h5a mirror [on\|off]` |
| **Mic / Speaker Volume & Denoise** | `AudioInputVolume`, `AudioOutputVolume`, `AudioInDenoise`, `Encode` | `dahua-h5a volume [--mic N] [--speaker N] [--denoise on\|off]` |
| **Built-in Siren / Audio Alarm** | `CoaxialControlIO` + `speak` + `Sound` | `dahua-h5a siren [status\|on\|off] [--duration S] [--volume N]` |
| **PTZ Pan / Tilt / Presets / Calibration** | `ptz.factory.instance` -> `ptz.start`, `ptz.stop`, `ptz.gotoPreset`, `ptz.restartPtz` | `dahua-h5a ptz <up\|down\|left\|right\|preset\|calibrate>` |
| **MicroSD Storage Telemetry** | `storage.getDeviceAllInfo` | `dahua-h5a storage` |
| **Real-Time Event Stream** | `eventManager.attach` -> `client.notifyEventStream` & `eventManager.getEventIndexes` | `dahua-h5a events` |
| **5MP RTSP Snapshot & Streams** | `rtsp://<host>:554/cam/realmonitor?channel=1&subtype=0\|1` | `dahua-h5a snapshot -o snap.jpg` |

---

## Installation

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

---

## Configuration (`.env` + SOPS)

Create a `.env` file (ignored by Git) with your camera connection parameters:

```ini
DAHUA_HOST=172.16.60.46
DAHUA_PORT=37777
DAHUA_RTSP_PORT=554
DAHUA_USERNAME=admin
DAHUA_PASSWORD=<your-camera-password>
```

---

## CLI Usage (`dahua-h5a`)

```bash
# Hardware, firmware, and RTSP URLs
dahua-h5a info

# Complete camera state (privacy, AI, LED, night vision, volumes, PTZ, MicroSD, active alarms)
dahua-h5a status

# Toggle Privacy Mode (physical lens mask)
dahua-h5a privacy on
dahua-h5a privacy off

# Toggle AI Human / Pet Detection & Auto-Tracking
dahua-h5a human-detect on
dahua-h5a pet-detect on
dahua-h5a smart-track on

# Status LED & Night Vision
dahua-h5a led off
dahua-h5a night-vision auto

# PTZ Control & Presets
dahua-h5a presets
dahua-h5a ptz left --speed 4 --duration 0.35
dahua-h5a ptz preset --index 1

# Capture 5MP JPEG Snapshot via RTSP
dahua-h5a snapshot -o snapshot.jpg

# Subscribe to real-time motion / human / pet / cry events
dahua-h5a events
```

---

## Python Async API Usage

```python
import asyncio
from aio_dahua_h5a import DahuaH5AClient


async def main() -> None:
    async with DahuaH5AClient(
        host="172.16.60.46",
        username="admin",
        password="...",
    ) as cam:
        info = await cam.get_device_info()
        print(f"Connected to {info.device_type} ({info.machine_name}) FW {info.software_version}")

        state = await cam.get_full_state()
        print("Privacy Mode:", state.privacy_mode)
        print("PTZ Position:", state.ptz.pan, state.ptz.tilt)
        print("SD Card Used %:", state.storage.used_percent)


asyncio.run(main())
```

---

## Running Tests

```bash
.venv/bin/pytest -v
```
