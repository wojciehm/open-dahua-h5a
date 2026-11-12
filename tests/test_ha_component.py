"""Tests for Home Assistant custom_components/dahua_h5a packaging and parity."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CC_DIR = REPO_ROOT / "custom_components" / "dahua_h5a"


def _collect_key_paths(obj: object, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            full = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                paths.update(_collect_key_paths(v, full))
            else:
                assert isinstance(v, str) and v.strip(), f"Empty translation at {full}"
                paths.add(full)
    return paths


def test_hacs_and_manifest_valid_json() -> None:
    """Verify hacs.json, manifest.json, and all translation files match strings.json."""
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    assert "name" in hacs

    manifest = json.loads((CC_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == "dahua_h5a"
    assert manifest["config_flow"] is True

    strings = json.loads((CC_DIR / "strings.json").read_text(encoding="utf-8"))
    expected_paths = _collect_key_paths(strings)

    translations_dir = CC_DIR / "translations"
    translation_files = sorted(translations_dir.glob("*.json"))
    expected_langs = {
        "cs.json",
        "de.json",
        "en.json",
        "es.json",
        "fr.json",
        "it.json",
        "ja.json",
        "nl.json",
        "pl.json",
        "pt.json",
        "uk.json",
        "zh-Hans.json",
    }
    assert expected_langs.issubset({f.name for f in translation_files})

    for tf in translation_files:
        data = json.loads(tf.read_text(encoding="utf-8"))
        actual_paths = _collect_key_paths(data)
        assert actual_paths == expected_paths, f"Key mismatch in {tf.name}"


def test_all_component_python_files_compile() -> None:
    """Ensure every Python module in custom_components/dahua_h5a parses cleanly."""
    py_files = list(CC_DIR.rglob("*.py"))
    assert len(py_files) >= 12
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8")
        ast.parse(source, filename=str(py_file))
