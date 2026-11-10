"""Command-line interface (`dahua-h5a`) for controlling Dahua H5A cameras locally."""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

from .client import DahuaH5AClient
from .exceptions import DahuaH5AError
from .models import CameraEvent


def _load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from `.env` into `os.environ` without overriding set vars."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in ("1", "true", "on", "yes", "enable", "enabled"):
        return True
    if v in ("0", "false", "off", "no", "disable", "disabled"):
        return False
    raise argparse.ArgumentTypeError(f"Expected on/off/true/false, got {value!r}")


def _build_parser() -> argparse.ArgumentParser:
    prog_name = "odh" if not sys.argv or not sys.argv[0] else Path(sys.argv[0]).name
    if prog_name.startswith("python"):
        prog_name = "odh"
    parser = argparse.ArgumentParser(
        prog=prog_name,
        description="Local Port 37777 NetSDK/JSON-RPC controller for Dahua H5A 360° cameras",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to .env file containing DAHUA_HOST, DAHUA_USERNAME, DAHUA_PASSWORD",
    )
    parser.add_argument("--host", default=None, help="Camera IP or hostname (env: DAHUA_HOST)")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Camera NetSDK TCP port (default: 37777, env: DAHUA_PORT)",
    )
    parser.add_argument(
        "--rtsp-port",
        type=int,
        default=None,
        help="Camera RTSP port (default: 554, env: DAHUA_RTSP_PORT)",
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Camera username (env: DAHUA_USERNAME)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Camera password (env: DAHUA_PASSWORD)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show full camera state, AI toggles, PTZ, and storage")

    # info
    sub.add_parser("info", help="Show hardware, firmware, and RTSP stream information")

    # privacy
    p_priv = sub.add_parser("privacy", help="Get or set Privacy Mode (physical lens mask)")
    p_priv.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # human-detect
    p_hum = sub.add_parser("human-detect", help="Get or set AI Human Detection")
    p_hum.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # pet-detect
    p_pet = sub.add_parser("pet-detect", help="Get or set AI Pet/Animal Detection")
    p_pet.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # smart-track
    p_trk = sub.add_parser("smart-track", help="Get or set Smart Auto-Tracking")
    p_trk.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # motion-detect
    p_mot = sub.add_parser("motion-detect", help="Get or set classic Motion Detection")
    p_mot.add_argument("state", nargs="?", type=_parse_bool, help="on / off")
    p_mot.add_argument(
        "--sensitivity",
        choices=["Low", "Middle", "High", "low", "middle", "high"],
        default=None,
        help="Set Smart Motion sensitivity (Low, Middle, High)",
    )

    # audio-detect
    p_aud = sub.add_parser(
        "audio-detect", help="Get or set Abnormal Sound / Baby Cry Detection"
    )
    p_aud.add_argument("state", nargs="?", type=_parse_bool, help="on / off")
    p_aud.add_argument(
        "--sensitivity",
        type=int,
        default=None,
        help="Anomaly audio sensitivity (1..100)",
    )

    # led
    p_led = sub.add_parser("led", help="Get or set front Status Indicator LED")
    p_led.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # night-vision
    p_nv = sub.add_parser("night-vision", help="Get or set Night Vision mode")
    p_nv.add_argument(
        "mode",
        nargs="?",
        choices=["auto", "night", "day", "ir", "off", "color", "bw"],
        help="auto | night | day",
    )

    # flip / mirror
    p_flip = sub.add_parser("flip", help="Get or set 180° vertical image flip")
    p_flip.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    p_mir = sub.add_parser("mirror", help="Get or set horizontal image mirror")
    p_mir.add_argument("state", nargs="?", type=_parse_bool, help="on / off")

    # volume
    p_vol = sub.add_parser("volume", help="Get or set microphone/speaker volume & denoise")
    p_vol.add_argument("--mic", type=int, default=None, help="Microphone volume (0..100)")
    p_vol.add_argument("--speaker", type=int, default=None, help="Speaker volume (0..100)")
    p_vol.add_argument("--denoise", type=_parse_bool, default=None, help="Audio denoise on/off")
    p_vol.add_argument(
        "--stream-audio", type=_parse_bool, default=None, help="RTSP stream audio on/off"
    )

    # siren
    p_sir = sub.add_parser("siren", help="Get status, configure, or trigger built-in siren")
    p_sir.add_argument("action", nargs="?", choices=["status", "on", "off"], default="status")
    p_sir.add_argument("--duration", type=int, default=None, help="Alarm duration in seconds")
    p_sir.add_argument("--volume", type=int, default=None, help="Alarm volume (0..100)")

    # ptz
    p_ptz = sub.add_parser("ptz", help="Control PTZ movement, presets, and calibration")
    p_ptz.add_argument(
        "action",
        choices=[
            "status",
            "up",
            "down",
            "left",
            "right",
            "left_up",
            "right_up",
            "left_down",
            "right_down",
            "stop",
            "preset",
            "set-preset",
            "del-preset",
            "calibrate",
        ],
        help="PTZ action or direction",
    )
    p_ptz.add_argument("--speed", type=int, default=4, help="Movement speed (1..8)")
    p_ptz.add_argument(
        "--duration",
        type=float,
        default=0.4,
        help="Movement step duration in seconds (0 = continuous without auto-stop)",
    )
    p_ptz.add_argument("--index", type=int, default=1, help="Preset index (default: 1)")
    p_ptz.add_argument("--name", default=None, help="Preset name for set-preset")

    # presets
    sub.add_parser("presets", help="List configured PTZ presets")

    # storage
    sub.add_parser("storage", help="Show MicroSD storage capacity and health")

    # snapshot
    p_snap = sub.add_parser("snapshot", help="Capture a JPEG snapshot from RTSP stream")
    p_snap.add_argument(
        "-o",
        "--output",
        default="snapshot.jpg",
        help="Output JPEG file path (default: snapshot.jpg)",
    )
    p_snap.add_argument(
        "--sub",
        action="store_true",
        help="Capture from Sub Stream (640x360) instead of Main 5MP Stream",
    )

    # events
    p_ev = sub.add_parser(
        "events", help="Monitor real-time camera events (Ctrl+C to stop)"
    )
    p_ev.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Optional duration in seconds (0 = listen indefinitely)",
    )

    # get-config / set-config / raw-rpc
    p_gcfg = sub.add_parser("get-config", help="Read a raw configuration table by name")
    p_gcfg.add_argument("name", help="Config table name (e.g., SmartMotionDetect, AELensMask)")

    p_scfg = sub.add_parser("set-config", help="Write a JSON configuration table by name")
    p_scfg.add_argument("name", help="Config table name")
    p_scfg.add_argument("table_json", help="JSON string for table value")

    p_rpc = sub.add_parser("raw-rpc", help="Execute a raw Port 37777 JSON-RPC method")
    p_rpc.add_argument("method", help="RPC method name (e.g., magicBox.getSoftwareVersion)")
    p_rpc.add_argument("--params", default=None, help="JSON string for params")
    p_rpc.add_argument("--object", type=int, default=None, help="Optional object ID")

    return parser


def _print_output(data: Any, as_json: bool) -> None:
    if dataclasses.is_dataclass(data):
        data = dataclasses.asdict(data)
    if as_json or isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)


async def _async_main(args: argparse.Namespace) -> int:
    # Load .env from explicit path, current dir, or parent /home/wojcieh/DevProjects/dahua/.env
    if args.env_file:
        _load_dotenv(Path(args.env_file))
    else:
        for candidate in (
            Path.cwd() / ".env",
            Path.cwd().parent / ".env",
            Path("/home/wojcieh/DevProjects/dahua/.env"),
        ):
            if candidate.is_file():
                _load_dotenv(candidate)
                break

    host = args.host or os.environ.get("DAHUA_HOST")
    username = args.username or os.environ.get("DAHUA_USERNAME")
    password = args.password or os.environ.get("DAHUA_PASSWORD")
    port = args.port or int(os.environ.get("DAHUA_PORT", "37777"))
    rtsp_port = args.rtsp_port or int(os.environ.get("DAHUA_RTSP_PORT", "554"))

    if not host or not username or not password:
        print(
            "Error: Missing camera credentials. Provide --host/--username/--password "
            "or set DAHUA_HOST, DAHUA_USERNAME, DAHUA_PASSWORD in .env.",
            file=sys.stderr,
        )
        return 2

    async with DahuaH5AClient(
        host=host,
        username=username,
        password=password,
        port=port,
        rtsp_port=rtsp_port,
    ) as client:
        cmd = args.command

        if cmd == "info":
            info = await client.get_device_info()
            payload = dataclasses.asdict(info)
            payload["rtsp_main_stream"] = client.get_rtsp_url(0, redact_password=True)
            payload["rtsp_sub_stream"] = client.get_rtsp_url(1, redact_password=True)
            _print_output(payload, args.json)
            return 0

        if cmd == "status":
            state = await client.get_full_state()
            _print_output(state, args.json)
            return 0

        if cmd == "privacy":
            if args.state is not None:
                await client.set_privacy_mode(args.state)
            cur = await client.get_privacy_mode()
            _print_output({"privacy_mode": cur}, args.json)
            return 0

        if cmd == "human-detect":
            if args.state is not None:
                await client.set_human_detection(args.state)
            cfg = await client.get_smart_motion_config()
            _print_output(
                {"human_detection": bool((cfg.get("ObjectTypes") or {}).get("Human", False))},
                args.json,
            )
            return 0

        if cmd == "pet-detect":
            if args.state is not None:
                await client.set_pet_detection(args.state)
            cfg = await client.get_smart_motion_config()
            _print_output(
                {"pet_detection": bool((cfg.get("ObjectTypes") or {}).get("Animal", False))},
                args.json,
            )
            return 0

        if cmd == "smart-track":
            if args.state is not None:
                await client.set_smart_track(args.state)
            cfg = await client.get_smart_motion_config()
            _print_output({"smart_track": bool(cfg.get("SmartTrack", False))}, args.json)
            return 0

        if cmd == "motion-detect":
            if args.state is not None:
                await client.set_motion_detection(args.state)
            if args.sensitivity is not None:
                await client.set_smart_sensitivity(args.sensitivity)
            mot = await client.get_motion_detection()
            scfg = await client.get_smart_motion_config()
            _print_output(
                {
                    "motion_detection": mot,
                    "smart_motion_enabled": bool(scfg.get("Enable", False)),
                    "smart_sensitivity": scfg.get("Sensitivity", "Middle"),
                },
                args.json,
            )
            return 0

        if cmd == "audio-detect":
            if args.state is not None or args.sensitivity is not None:
                await client.set_audio_detection(
                    enabled=args.state,
                    sensitivity=args.sensitivity,
                )
            acfg = await client.get_audio_detection()
            _print_output(
                {
                    "audio_detection": bool(acfg.get("Enable", False)),
                    "anomaly_enabled": bool(acfg.get("AnomalyDetect", False)),
                    "anomaly_sensitivity": int(acfg.get("AnomalySensitive", 50)),
                },
                args.json,
            )
            return 0

        if cmd == "led":
            if args.state is not None:
                await client.set_status_led(args.state)
            led = await client.get_status_led()
            _print_output({"status_led": led}, args.json)
            return 0

        if cmd == "night-vision":
            if args.mode is not None:
                await client.set_night_vision(args.mode)
            nv = await client.get_night_vision()
            _print_output(nv, args.json)
            return 0

        if cmd == "flip":
            if args.state is not None:
                await client.set_mirror_flip(flip=args.state)
            orient = await client.get_image_orientation()
            _print_output(orient, args.json)
            return 0

        if cmd == "mirror":
            if args.state is not None:
                await client.set_mirror_flip(mirror=args.state)
            orient = await client.get_image_orientation()
            _print_output(orient, args.json)
            return 0

        if cmd == "volume":
            if args.mic is not None:
                await client.set_mic_volume(args.mic)
            if args.speaker is not None:
                await client.set_speaker_volume(args.speaker)
            if args.denoise is not None:
                await client.set_audio_denoise(args.denoise)
            if args.stream_audio is not None:
                await client.set_stream_audio(args.stream_audio)
            _print_output(
                {
                    "mic_volume": await client.get_mic_volume(),
                    "speaker_volume": await client.get_speaker_volume(),
                    "audio_denoise": await client.get_audio_denoise(),
                    "stream_audio_enabled": await client.get_stream_audio(),
                },
                args.json,
            )
            return 0

        if cmd == "siren":
            if args.duration is not None or args.volume is not None:
                await client.set_siren_config(duration=args.duration, volume=args.volume)
            if args.action == "on":
                await client.trigger_siren(True)
            elif args.action == "off":
                await client.trigger_siren(False)
            _print_output(await client.get_siren_status(), args.json)
            return 0

        if cmd == "presets":
            presets = await client.ptz_get_presets()
            _print_output([dataclasses.asdict(p) for p in presets], args.json)
            return 0

        if cmd == "ptz":
            act = args.action
            if act == "status":
                _print_output(await client.ptz_status(), args.json)
            elif act == "stop":
                await client.ptz_stop()
                _print_output(await client.ptz_status(), args.json)
            elif act == "preset":
                await client.ptz_goto_preset(args.index)
                _print_output({"goto_preset": args.index, "result": True}, args.json)
            elif act == "set-preset":
                name = args.name or f"Preset{args.index}"
                await client.ptz_set_preset(args.index, name)
                _print_output(
                    {"set_preset": args.index, "name": name, "result": True},
                    args.json,
                )
            elif act == "del-preset":
                await client.ptz_remove_preset(args.index)
                _print_output({"remove_preset": args.index, "result": True}, args.json)
            elif act == "calibrate":
                await client.ptz_restart()
                _print_output({"calibrate": True}, args.json)
            else:
                if args.duration > 0:
                    await client.ptz_step(act, speed=args.speed, duration=args.duration)
                else:
                    await client.ptz_start(act, speed=args.speed)
                _print_output(await client.ptz_status(), args.json)
            return 0

        if cmd == "storage":
            _print_output(await client.get_storage_info(), args.json)
            return 0

        if cmd == "snapshot":
            subtype = 1 if args.sub else 0
            img = await client.capture_snapshot(args.output, subtype=subtype)
            _print_output(
                {
                    "output": str(Path(args.output).resolve()),
                    "bytes": len(img),
                    "subtype": subtype,
                },
                args.json,
            )
            return 0

        if cmd == "events":
            def _on_event(ev: CameraEvent) -> None:
                print(json.dumps(dataclasses.asdict(ev), ensure_ascii=False), flush=True)

            client.register_event_callback(_on_event)
            sid = await client.attach_events(["All"])
            active_now = await client.get_active_events()
            print(
                json.dumps({"attached_sid": sid, "active_events": active_now}),
                flush=True,
            )
            if args.duration > 0:
                await asyncio.sleep(args.duration)
            else:
                while True:
                    await asyncio.sleep(1.0)
            return 0

        if cmd == "get-config":
            table = await client.get_config(args.name)
            _print_output({"name": args.name, "table": table}, args.json)
            return 0

        if cmd == "set-config":
            table_val = json.loads(args.table_json)
            ok = await client.set_config(args.name, table_val)
            _print_output({"name": args.name, "result": ok}, args.json)
            return 0

        if cmd == "raw-rpc":
            params = json.loads(args.params) if args.params else None
            res = await client.rpc(args.method, params, object_id=args.object)
            _print_output(res, args.json)
            return 0

    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args()
    try:
        rc = asyncio.run(_async_main(args))
    except KeyboardInterrupt:
        rc = 0
    except DahuaH5AError as err:
        print(f"Error: {err}", file=sys.stderr)
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
