#!/usr/bin/env python3
"""Static extractor for RPC methods and config tables from unpacked Dahua binaries."""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

RPC_PATTERN = re.compile(
    rb"\b([A-Za-z][A-Za-z0-9_]{2,32}\.(?:factory\.instance|[a-z][A-Za-z0-9_]{2,40}))\b"
)

KNOWN_COMPONENTS = {
    "global",
    "magicBox",
    "configManager",
    "ptz",
    "PtzFunc",
    "PtzIntelli",
    "eventManager",
    "alarm",
    "devVideoInput",
    "devVideoOutput",
    "devAudioInput",
    "devAudioOutput",
    "speak",
    "RemoteSpeak",
    "storage",
    "devStorage",
    "userManager",
    "netApp",
    "WLan",
    "CoaxialControlIO",
    "OneKeyMaskVideo",
    "mediaFileFind",
    "snapManager",
    "LensFunc",
    "log",
    "ntp",
    "LeChange",
}


def extract_rpc_methods(re_workspace: Path) -> list[str]:
    found: set[str] = set()
    binaries = (
        glob.glob(str(re_workspace / "**/*.so"), recursive=True)
        + glob.glob(str(re_workspace / "**/*.dll"), recursive=True)
    )
    for path in binaries:
        if not any(
            k in path.lower()
            for k in ("netsdk", "configsdk", "avnetsdk", "lcbusiness")
        ):
            continue
        data = Path(path).read_bytes()
        for match in RPC_PATTERN.finditer(data):
            s = match.group(1).decode("ascii", errors="ignore")
            comp = s.split(".", 1)[0]
            if comp in KNOWN_COMPONENTS:
                found.add(s)
    return sorted(found)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    re_ws = Path("/home/wojcieh/DevProjects/dahua/re_workspace")
    methods = extract_rpc_methods(re_ws)
    print(f"Extracted {len(methods)} unique RPC methods across vendor SDK binaries.")
    out_path = Path(__file__).resolve().parent.parent / "docs" / "extracted_sdk_methods.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(methods, indent=2) + "\n", encoding="utf-8")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
