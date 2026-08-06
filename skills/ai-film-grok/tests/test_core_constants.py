"""P4-1: first unit tests for core.constants (zero-coverage foundation)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core import constants as C  # noqa: E402


def test_schema_and_manifest_names() -> None:
    assert C.SCHEMA_VERSION == 2
    assert C.MANIFEST_NAME == "manifest.json"
    assert C.DIRECTOR_NOTES_NAME.endswith(".json")


def test_default_geometry_is_portrait() -> None:
    assert C.DEFAULT_FPS > 0
    assert C.DEFAULT_WIDTH > 0
    assert C.DEFAULT_HEIGHT > C.DEFAULT_WIDTH  # 9:16 portrait


def test_gate_order_is_unique_and_starts_with_brief() -> None:
    assert C.GATE_ORDER[0] == "brief"
    assert len(C.GATE_ORDER) == len(set(C.GATE_ORDER))
    assert "final_complete" in C.GATE_ORDER
    assert "desktop_exported" in C.GATE_ORDER


def test_export_metadata_files_cover_core_artifacts() -> None:
    names = set(C.EXPORT_METADATA_FILES)
    for required in ("brief.json", "film-spec.json", "manifest.json", "timeline.json"):
        assert required in names


def test_native_audio_audible_floor_is_negative() -> None:
    assert C.NATIVE_AUDIO_AUDIBLE_MIN_DB < 0
