"""Lock util soft/strict JSON contract (optimization loop + P1a)."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from util import (  # noqa: E402
    read_json,
    require_json,
    require_json_as,
    require_json_fnv,
    soft_json,
    write_json,
)
from util.errors import FilmError  # noqa: E402


def test_soft_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_json(tmp_path / "nope.json") is None


def test_soft_read_invalid_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    assert read_json(path) is None


def test_soft_json_always_dict(tmp_path: Path) -> None:
    assert soft_json(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("[1,2]", encoding="utf-8")
    assert soft_json(bad) == {}
    ok = tmp_path / "ok.json"
    write_json(ok, {"k": 1})
    assert soft_json(ok) == {"k": 1}


def test_require_json_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FilmError, match="Missing JSON"):
        require_json(tmp_path / "nope.json")


def test_require_json_as_maps_domain_error(tmp_path: Path) -> None:
    class DomainErr(RuntimeError):
        pass

    with pytest.raises(DomainErr, match="Missing JSON"):
        require_json_as(tmp_path / "nope.json", DomainErr)
    path = tmp_path / "ok.json"
    write_json(path, {"x": 2})
    assert require_json_as(path, DomainErr) == {"x": 2}


def test_require_json_fnv_legacy_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Missing JSON"):
        require_json_fnv(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        require_json_fnv(bad)


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


def test_final_stages_uses_soft_json_not_local_def() -> None:
    import final_stages

    src = inspect.getsource(final_stages)
    assert "def _read_json" not in src
    assert "soft_json" in src
