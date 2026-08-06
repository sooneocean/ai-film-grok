"""P4-1: first unit tests for util.spine_helpers pure helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from util.spine_helpers import export_desktop_name, present  # noqa: E402


def test_present_requires_file_and_min_bytes(tmp_path: Path) -> None:
    missing = tmp_path / "nope.bin"
    assert present(missing) is False
    tiny = tmp_path / "tiny.bin"
    tiny.write_bytes(b"x")
    assert present(tiny, min_bytes=2) is False
    ok = tmp_path / "ok.bin"
    ok.write_bytes(b"abc")
    assert present(ok, min_bytes=2) is True


def test_export_desktop_name_prefers_film_spec_title(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"title": "宿色 EP01"}), encoding="utf-8"
    )
    name = export_desktop_name(tmp_path)
    assert "宿色" in name or "EP01" in name
    assert " " not in name


def test_export_desktop_name_fallback_when_empty(tmp_path: Path) -> None:
    assert export_desktop_name(tmp_path) == "film"
