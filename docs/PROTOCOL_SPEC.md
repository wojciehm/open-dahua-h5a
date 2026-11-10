# Dahua H5A (DH-H5A / IPC-H5A) Local Control Protocol Specification

> **Clean-Room Reverse Engineering Reference**  
> Reconstructed from static binary analysis of `libdhnetsdk.so` / `libdhconfigsdk.so` (macOS ConfigTool), `libnetsdk.so` / `libconfigsdk.so` (Android DMSS 2.6.22), and `dhnetsdk.dll` / `avnetsdk.dll` (Windows ConfigTool), verified live against **Dahua H5A 5MP 360° Wi-Fi 6** (`V2.860.0000000.26.R`, build `2026-05-30`).

---

## 1. Architecture Overview & Why Port 80 HTTP CGI Returns 404

Unlike older Dahua IPC models that expose an embedded web UI and `/cgi-bin/*.cgi` endpoints on TCP port `80`, the consumer/IoT **Dahua H5A (`DH-H5A`)** explicitly disables local web services in firmware. Querying `magicBox.getProductDefinition` over Port `37777` returns:

```json
{
  "DeviceWebCaps": {
    "SupportLocalWebSource": false,
    "SupportWebService": false
  }
}
```

Consequently:
- **TCP Port `80`**: Hosts **only** the embedded `gSOAP/2.8` ONVIF server (`/onvif/device_service`, `/onvif/media_service`, `/onvif/ptz_service`). All `/cgi-bin/*` and `/RPC2*` HTTP paths return `404 Not Found`.
- **TCP Port `554`**: Standard RTSP server (`Rtsp Server/3.0.0`) with RFC 2617 HTTP Digest Authentication, serving 5MP H.265 Main Stream (`subtype=0`) and 640x360 Sub Stream (`subtype=1`) with bidirectional AAC audio.
- **TCP Port `37777`**: **Dahua NetSDK DVR2 Binary Protocol + Embedded JSON-RPC (`0xf6`)**. Provides **100% of camera configuration, AI toggles, privacy mask, LED, night vision, PTZ, siren, storage, and real-time event streaming**.

---

## 2. Port `37777` DVR2 Binary Framing

Every packet exchanged on TCP port `37777` starts with a fixed **32-byte little-endian header**, followed by `ext_len` bytes of payload (`uint32_le` at offset `4..8`).

| Byte Offset | Type | Field | Description |
| :--- | :--- | :--- | :--- |
| `0` | `uint8` | `cmd` | Command opcode (`0xa0` = Login Request, `0xb0` = Login Response, `0xf6` = JSON-RPC Frame) |
| `1..3` | `uint8[3]` | `magic` | Header flags (`0x05 0x00 0x60` for `0xa0` login, `0x00 0x00 0x00` for `0xf6` RPC) |
| `4..7` | `uint32_le` | `ext_len` | Payload length of **this packet chunk** in bytes |
| `8..11` | `uint32_le` | `req_id` / `status` | Sequence/request ID for `0xf6` (`seq_id << 8`); status/error bytes for `0xb0` login response |
| `12..15` | `uint32_le` | `subcmd` | Sub-command / flags (`0` on main connection) |
| `16..19` | `uint32_le` | `total_len` / `session` | In `0xb0` Step 2 response: assigned `session_id`. In `0xf6` RPC: **total unfragmented JSON payload length** |
| `20..23` | `uint32_le` | `reserved` | `0` |
| `24..27` | `uint32_le` | `session_id` / `login_flags` | In `0xf6` RPC: **active `session_id`** (mandatory on main connection) |
| `28..31` | `uint32_le` | `tail_flags` | Login magic `0x00 0x00 0xa1 0xaa` during `0xa0` handshake; `0` during `0xf6` RPC |

---

## 3. Two-Step `0xa0` Challenge-Response Authentication & `DH_Superencipherment`

### Step 1: Request Digest Challenge (`0xa0` -> `0xb0`)

Client sends a 32-byte `0xa0` packet with zero payload (`ext_len = 0`):

```
a0 05 00 60  00 00 00 00  00 00 00 00  00 00 00 00
00 00 00 00  00 00 00 00  01 02 00 01  3c 00 a1 aa
```

Camera responds with `0xb0` (`resp[8] = 0x01`, `resp[9] = 0x0e` = challenge required) and an ASCII body:

```text
Realm:Login to FF8A7CD1282D3D39\r\n
Random:2112708297\r\n\r\n
```

### Step 2: Compute Dual Digest (`H1 + H2`) & Authenticate

Disassembly of `OnCheckPasswordPacket` (`0x1eb00`) and `DH_Superencipherment` (`0x285610`) in `libdhnetsdk.so` reveals that the camera requires a **64-character concatenated token** (`H1 + H2`):

1. **Standard Realm MD5 (`H1`)**:
   ```python
   A1 = MD5_HEX_UPPER(f"{username}:{realm}:{password}")
   H1 = MD5_HEX_UPPER(f"{username}:{random}:{A1}")
   ```
2. **Dahua Base62 `DH_Superencipherment` (`H2`)**:
   - Compute the raw 16-byte MD5 digest `d[0..15]` of `password`.
   - Map each of the 8 byte-pairs `(d[2*i] + d[2*i+1]) % 62` into the 62-character alphabet `"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"` to produce an 8-character string `dh_pwd`.
   - Compute:
     ```python
     H2 = MD5_HEX_UPPER(f"{username}:{random}:{dh_pwd}")
     ```
3. **Construct `ext2` Payload**:
   ```python
   ext2 = f"{username}&&{H1}{H2}".encode("utf-8")
   ```
4. **Send Step 2 `0xa0` Packet**:
   - `pkt[0:4] = b"\xa0\x05\x00\x60"`
   - `pkt[4:8] = uint32_le(len(ext2))`
   - `pkt[24:32] = b"\x01\x02\x00\x08\x00\x00\xa1\xaa"`
   - Append `ext2`.
5. **Verify Step 2 `0xb0` Response**:
   - `resp[8] == 0x00` indicates authentication success.
   - `session_id = uint32_le(resp[16:20])` is the active session identifier for all subsequent `0xf6` calls.

---

## 4. JSON-RPC (`0xf6`) Request & Multi-Packet Response Reassembly

Reconstructed from `sendJsonPacket_dvr2` (`0x453910` in `libdhnetsdk.so`):
- On the main NetSDK connection (`subconn_id == -1`), **no 4-byte prefix** is prepended to the JSON body (`hdr[14] = 0`), and **`session_id` MUST be written to `hdr[24:28]`**:
  ```python
  json_bytes = json.dumps(req, separators=(",", ":")).encode("utf-8") + b"\n\x00"
  hdr = bytearray(32)
  hdr[0] = 0xF6
  struct.pack_into("<I", hdr, 4, len(json_bytes))
  struct.pack_into("<I", hdr, 8, req_id)       # req_id = seq_id << 8
  struct.pack_into("<I", hdr, 16, len(json_bytes))
  struct.pack_into("<I", hdr, 24, session_id)
  ```
- **Multi-Packet Response Reassembly**:
  Large responses (e.g., `magicBox.getProductDefinition` or `configManager.getMemberNames`) are split across multiple `0xf6` frames sharing the same `req_id`. Each frame carries `chunk_len = uint32_le(hdr[4:8])` and `total_len = uint32_le(hdr[16:20])`. The client concatenates chunks until `len(buffer) >= total_len`, strips trailing `\n\x00`, and parses UTF-8 JSON.

---

## 5. Complete H5A Control & Configuration Mapping

### 5.1 Configuration Tables (`configManager.getConfig` / `configManager.setConfig`)

| Feature | Config Table (`name`) | JSON Path (`table`) | Values |
| :--- | :--- | :--- | :--- |
| **Privacy Mode (Physical Lens Mask)** | `AELensMask` | `table[0]["Status"]` (`Enable: true`) | `true` (lens closed/masked), `false` (lens open) |
| **AI Human Detection** | `SmartMotionDetect` | `table[0]["ObjectTypes"]["Human"]` | `true` / `false` |
| **AI Pet / Animal Detection** | `SmartMotionDetect` | `table[0]["ObjectTypes"]["Animal"]` | `true` / `false` |
| **Smart Auto-Tracking** | `SmartMotionDetect` | `table[0]["SmartTrack"]` | `true` / `false` |
| **Smart Motion Sensitivity** | `SmartMotionDetect` | `table[0]["Sensitivity"]` | `"Low"`, `"Middle"`, `"High"` |
| **Classic Motion Detection** | `MotionDetect` | `table[0]["Enable"]` | `true` / `false` |
| **Abnormal Sound / Cry Detection** | `AudioDetect` | `table[0]["Enable"]`, `table[0]["AnomalyDetect"]` | `true` / `false`, `AnomalySensitive`: `1..100` |
| **Status Indicator LED** | `LightGlobal` | `table[0]["Enable"]` | `true` / `false` |
| **Night Vision IR Illuminator** | `Lighting` | `table[0][0]["Mode"]` | `"Auto"`, `"Manual"`, `"Off"` |
| **Day/Night ICR Filter Mode** | `VideoInDayNight` | `table[0][0]["Mode"]` | `"Brightness"` (Auto), `"Color"` (Day), `"BlackWhite"` (Night) |
| **Image Mirror / 180° Flip** | `VideoInOptions` & `VideoImageControl` | `table[0]["Mirror"]`, `table[0]["Flip"]`, `Rotate90` | `true` / `false`, `Rotate90`: `0..3` |
| **Microphone Volume** | `AudioInputVolume` | `table[0]` | `0..100` (`int`) |
| **Speaker Volume** | `AudioOutputVolume` | `table[0]` | `0..100` (`int`) |
| **Microphone Noise Reduction** | `AudioInDenoise` | `table[0]["enable"]` | `true` / `false` |
| **RTSP Stream Audio Enable** | `Encode` | `table[0]["MainFormat"][0]["AudioEnable"]` | `true` / `false` |
| **Siren Sound & Duration** | `Sound` | `AlarmSound`, `AlarmSoundDuration`, `AlarmSoundVolume` | `"/usr/data/audiofiles/siren/alarm.wav"`, `1..300` s, `0..100` |

### 5.2 Object-Oriented RPC Services (`ptz`, `speak`, `CoaxialControlIO`, `storage`, `eventManager`)

1. **PTZ Service (`HorizontalAngle: [0, 355]`, `VerticalAngle: [-14, 90]`)**:
   - Instantiate handle: `ptz.factory.instance({"channel": 0})` -> returns integer `object_id` in `"result"` (typically `2`).
   - Continuous movement:
     - `ptz.start({"code": "<Up|Down|Left|Right|LeftUp|RightUp|LeftDown|RightDown>", "arg1": 0, "arg2": speed, "arg3": 0}, object=object_id)`
     - `ptz.stop({"code": "<direction>", "arg1": 0, "arg2": 1, "arg3": 0}, object=object_id)`
   - Presets:
     - `ptz.getPresets(None, object=object_id)` -> `{"presets": [{"Index": 1, "Name": "Sypialnia"}]}`
     - `ptz.gotoPreset({"index": 1}, object=object_id)` or `ptz.start({"code": "GotoPreset", "arg1": 1, "arg2": 0, "arg3": 0}, object=object_id)`
     - `ptz.setPreset({"index": idx, "name": name}, object=object_id)`
     - `ptz.removePreset({"index": idx}, object=object_id)`
   - Status & Calibration:
     - `ptz.getStatus(None, object=object_id)`
     - `ptz.restartPtz(None, object=object_id)`

2. **Siren & Speaker Service (`CoaxialControlIO` & `speak`)**:
   - Query status: `CoaxialControlIO.getStatus({"channel": 0})` -> `{"status": {"WhiteLight": "Off", "Speaker": "Off"}}`
   - Instantiate speaker handle: `speak.factory.instance({"channel": 0})` -> `object_id`
   - Query playback status: `speak.getStatus(None, object=object_id)` -> `{"Info": {"Status": 0, "PlayTimeLeft": 0}}`
   - Trigger / Stop siren: `CoaxialControlIO.control` and `speak.startPlay` / `speak.stopPlay`.

3. **Real-Time Events (`eventManager`)**:
   - Supported event codes (`eventManager.getSupportEventDetailList`):
     - Channel 0: `VideoMotion`, `SmartMotionHuman`, `SmartMotionAnimal`, `VideoBlind`
     - Device: `AudioMutation` (Abnormal Sound / Cry), `StorageFailure`, `StorageNotExist`, `StorageLowSpace`, `NetAbort`, `IPConflict`
   - Poll active events: `eventManager.getEventIndexes({"code": "<EventCode>"})` -> returns `{"indexes": [0]}` while active, `{}` when idle.
   - Real-time push stream: `eventManager.attach({"codes": ["All"]})` -> returns `{"SID": <int>}` and streams `{"method": "client.notifyEventStream", "params": {"SID": ..., "eventList": [{"Code": "...", "Action": "Start|Stop|Pulse", "Index": 0, "Data": {...}}]}}`.

4. **RTSP Streams (Port `554`)**:
   - **Main Stream (5MP `2880x1620` H.265 @ 20fps + AAC 16kHz)**:
     `rtsp://<user>:<password>@<host>:554/cam/realmonitor?channel=1&subtype=0`
   - **Sub Stream (`640x360` + AAC)**:
     `rtsp://<user>:<password>@<host>:554/cam/realmonitor?channel=1&subtype=1`
