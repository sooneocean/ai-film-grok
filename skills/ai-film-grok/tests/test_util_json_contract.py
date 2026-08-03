"""Lock util soft/strict JSON contract (optimization loop)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from util import read_json, require_json, write_json  # noqa: E402
from util.errors import FilmError  # noqa: E402


def test_soft_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_json(tmp_path / "nope.json") is None


def test_soft_read_invalid_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    assert read_json(path) is None


def test_require_json_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FilmError, match="Missing JSON"):
        require_json(tmp_path / "nope.json")


def test_require_and_write_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    write_json(path, {"a": 1, "中": "文"})
    assert require_json(path) == {"a": 1, "中": "文"}
    raw = path.read_text(encoding="utf-8")
    assert "文" in raw
    assert json.loads(raw)["a"] == 1


def test_json_io_legacy_strict_facade(tmp_path: Path) -> None:
    from util import json_io

    path = tmp_path / "legacy.json"
    json_io.write_json(path, {"ok": True})
    assert json_io.read_json(path)["ok"] is True
    with pytest.raises(FilmError):
        json_io.read_json(tmp_path / "missing.json")
