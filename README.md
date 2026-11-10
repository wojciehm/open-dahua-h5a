# open-dahua-h5a (`aio-dahua-h5a` & Home Assistant HACS Integration)

Clean-room, dependency-free **Home Assistant Custom Integration (`custom_components/dahua_h5a`)**, **async Python library (`aio_dahua_h5a`)**, and **CLI (`dahua-h5a`)** for 100% local control of **Dahua H5A 5MP 360° Indoor Wi-Fi 6 (`DH-H5A` / `IPC-H5A`)** and Hero-series cameras over **TCP Port `37777` (NetSDK DVR2 `0xa0` + Embedded JSON-RPC `0xf6`)** and **RTSP Port `554`**.

> **Legal & Interoperability Notice (EU Directive 2009/24/EC Art. 6 & § 69e UrhG):**  
> This clean-room open-source project was created **solely for interoperability**—enabling legal owners of Dahua H5A / Hero-series cameras to integrate their own hardware with open-source smart home systems (**Home Assistant**) on a local network, in accordance with **Article 6 of EU Directive 2009/24/EC** and **§ 69e of the German Copyright Act (UrhG)**.  
> - **No circumvention of security or access controls:** Valid administrator credentials (`username` and `password`) for the device are strictly required.  
> - **Zero vendor code:** This repository contains **no** proprietary Dahua SDK libraries, binary blobs, or firmware files—only an independent Python `asyncio` implementation built from scratch by **Google Antigravity**.  
> - **No affiliation:** Not affiliated with, endorsed by, or supported by Dahua Technology.

---

## Why Port `37777` Instead of HTTP Port `80`?

On the consumer/IoT **Dahua H5A (`DH-H5A`)**, firmware `V2.860.0000000.26.R` explicitly disables the legacy HTTP Web UI and `/cgi-bin/*.cgi` API (`"DeviceWebCaps": {"SupportLocalWebSource": false, "SupportWebService": false}`). Port `80` only runs an embedded `gSOAP/2.8` ONVIF endpoint, while **Port `37777`** exposes the complete JSON-RPC control plane encapsulated inside 32-byte DVR2 binary frames (`0xa0` login + `0xf6` JSON-RPC).

See [`docs/PROTOCOL_SPEC.md`](docs/PROTOCOL_SPEC.md) for the full byte-level specification, including the `DH_Superencipherment` Base62 password hash and `0xf6` frame reassembly rules, and [`docs/h5a_capabilities.json`](docs/h5a_capabilities.json) for the complete camera capability and RPC method dump.

---

## Home Assistant Integration (HACS — Multi-Camera UI Workflow)

The repository is structured as a ready-to-install **HACS Integration** (`custom_components/dahua_h5a` + `hacs.json`) with a full UI `ConfigFlow` (no YAML or static files required):

1. Open **HACS** in Home Assistant -> **Custom repositories** -> add `https://github.com/wojciehm/open-dahua-h5a` with category **Integration**.
2. Click **Download** and restart Home Assistant.
3. Go to **Settings -> Devices & Services -> Add Integration** and search for **Dahua H5A (Local NetSDK)**.
4. Enter your camera's **IP / Hostname**, **NetSDK Port (`37777`)**, **RTSP Port (`554`)**, **Username (`admin`)**, and **Password**.
5. Repeat **Add Integration** for as many cameras as you have—each camera is uniquely identified by its hardware serial number (`magicBox.getSerialNo`) and maintains its own isolated TCP `37777` connection and real-time event stream.

### Exposed Home Assistant Entities (per camera)

- **Camera**: 5MP H.265 Live Stream (`subtype=0`) or Sub Stream (`subtype=1`), RTSP JPEG Snapshots, Turn On/Off mapped to physical Privacy Shutter, plus entity services (`dahua_h5a.ptz_move`, `dahua_h5a.ptz_goto_preset`, `dahua_h5a.ptz_set_preset`, `dahua_h5a.ptz_remove_preset`, `dahua_h5a.trigger_siren`).
- **Switches (10)**: Privacy Mask (Hide Lens), AI Human Detection, AI Pet Detection, AI Smart Auto-Tracking, Motion Detection, Abnormal Sound / Baby Cry Detection, Status Indicator LED, Stream Audio Recording, Image Mirror, Image Flip (180° Ceiling Mount).
- **Selects (2)**: Night Vision IR Mode (`auto` / `off` / `on`), Dynamic PTZ Preset Selector.
- **Numbers (3)**: Speaker Volume (`0–100%`), Microphone Sensitivity (`0–100%`), Sound Detection Sensitivity (`1–100%`).
- **Buttons (6)**: PTZ Up, PTZ Down, PTZ Left, PTZ Right, Trigger Siren, Calibrate PTZ.
- **Binary Sensors (4)**: Motion (`VideoMotion`), Person Detected (`SmartMotionHuman`), Sound / Cry Detected (`AudioMutation` / `BabyCry`), Privacy Shutter Closed.
- **Sensors (5)**: MicroSD Card Status, MicroSD Used (`%`), MicroSD Free Space (`GB`), PTZ Pan Angle, PTZ Tilt Angle.

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

## Standalone Python Library & CLI Installation

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
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
