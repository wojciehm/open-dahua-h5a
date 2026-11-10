"""Tests for Home Assistant custom_components/dahua_h5a packaging and parity."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CC_DIR = REPO_ROOT / "custom_components" / "dahua_h5a"


def test_hacs_and_manifest_valid_json() -> None:
    """Verify hacs.json, manifest.json, and translation files are valid JSON."""
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert "name" in hacs

    manifest = json.loads((CC_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "dahua_h5a"
    assert manifest["config_flow"] is True

    strings = json.loads((CC_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((CC_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    pl = json.loads((CC_DIR / "translations" / "pl.json").read_text(encoding="utf-8"))

    assert set(strings["entity"].keys()) == set(en["entity"].keys())
    assert set(strings["entity"].keys()) == set(pl["entity"].keys())
    assert "reconfigure" in pl["config"]["step"]


def test_all_component_python_files_compile() -> None:
    """Ensure every Python module in custom_components/dahua_h5a parses cleanly."""
    py_files = list(CC_DIR.rglob("*.py"))
    assert len(py_files) >= 12
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8")
        ast.parse(source, filename=str(py_file))
