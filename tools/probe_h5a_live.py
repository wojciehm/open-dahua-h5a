#!/usr/bin/env python3
"""Live capability probe for the Dahua H5A camera (sanitizes all sensitive fields)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aio_dahua_h5a.cli import _load_dotenv
from aio_dahua_h5a.client import DahuaH5AClient

COMPONENTS_TO_PROBE = [
    "global",
    "magicBox",
    "configManager",
    "ptz",
    "eventManager",
    "alarm",
    "devVideoInput",
    "devAudioInput",
    "devAudioOutput",
    "speak",
    "storage",
    "userManager",
    "netApp",
    "WLan",
    "CoaxialControlIO",
    "mediaFileFind",
    "log",
]


async def probe() -> dict[str, Any]:
    for candidate in (
        Path.cwd() / ".env",
        Path.cwd().parent / ".env",
        Path("/home/wojcieh/DevProjects/dahua/.env"),
    ):
        if candidate.is_file():
            _load_dotenv(candidate)
            break

    host = os.environ["DAHUA_HOST"]
    user = os.environ["DAHUA_USERNAME"]
    pwd = os.environ["DAHUA_PASSWORD"]
    port = int(os.environ.get("DAHUA_PORT", "37777"))

    async with DahuaH5AClient(host, user, pwd, port=port) as client:
        info = await client.get_device_info()
        member_names = await client.get_member_names()
        component_methods: dict[str, list[str]] = {}
        for comp in COMPONENTS_TO_PROBE:
            resp = await client.rpc(f"{comp}.listMethod")
            if resp.get("result"):
                component_methods[comp] = (resp.get("params") or {}).get("method") or []

        ptz_obj = (await client.rpc("ptz.factory.instance", {"channel": 0}))["result"]
        ptz_methods = (
            (await client.rpc("ptz.listMethod", None, object_id=ptz_obj)).get("params")
            or {}
        ).get("method") or []
        component_methods["ptz (instance)"] = ptz_methods

        speak_obj = (await client.rpc("speak.factory.instance", {"channel": 0}))[
            "result"
        ]
        speak_methods = (
            (
                await client.rpc("speak.listMethod", None, object_id=speak_obj)
            ).get("params")
            or {}
        ).get("method") or []
        component_methods["speak (instance)"] = speak_methods

        prod_def = (
            (await client.rpc("magicBox.getProductDefinition")).get("params") or {}
        ).get("definition") or {}
        coax_caps = (
            (await client.rpc("CoaxialControlIO.getCaps", {"channel": 0})).get("params")
            or {}
        ).get("caps") or {}
        speak_caps = (
            (await client.rpc("speak.getCaps", {"channel": 0})).get("params") or {}
        ).get("caps") or {}
        ev_details = (
            await client.rpc("eventManager.getSupportEventDetailList")
        ).get("params") or {}

        return {
            "device": {
                "model": info.device_type,
                "hardware_version": info.hardware_version,
                "software_version": info.software_version,
                "build_date": info.build_date,
                "vendor": info.vendor,
            },
            "ports": {
                "netsdk_dvr2_jsonrpc": 37777,
                "rtsp": 554,
                "onvif_http": 80,
            },
            "product_definition": prod_def,
            "coaxial_io_caps": coax_caps,
            "speak_caps": speak_caps,
            "supported_events": ev_details,
            "config_table_names": member_names,
            "rpc_component_methods": component_methods,
        }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data = asyncio.run(probe())
    out_path = Path(__file__).resolve().parent.parent / "docs" / "h5a_capabilities.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote sanitized capabilities profile to {out_path}")


if __name__ == "__main__":
    main()
