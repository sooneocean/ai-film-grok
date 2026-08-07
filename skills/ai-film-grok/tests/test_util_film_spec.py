"""C6.4 base contracts for util.film_spec (strict vs soft load + shot iter)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from util.errors import FilmError  # noqa: E402
from util.film_spec import _iter_shots, _load_spec, _root, soft_load_spec  # noqa: E402


def test_root_expand_and_resolve(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    resolved = _root(nested)
    assert resolved.is_absolute()
    assert resolved == nested.resolve()


def test_soft_load_spec_missing_returns_empty(tmp_path: Path) -> None:
    assert soft_load_spec(tmp_path) == {}


def test_soft_load_spec_invalid_json_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{not-json", encoding="utf-8")
    assert soft_load_spec(tmp_path) == {}


def test_soft_load_spec_valid(tmp_path: Path) -> None:
    payload = {"title": "t", "scenes": []}
    (tmp_path / "film-spec.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert soft_load_spec(tmp_path) == payload


def test_load_spec_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FilmError):
        _load_spec(tmp_path)


def test_load_spec_valid(tmp_path: Path) -> None:
    payload = {"scenes": [{"shots": [{"id": "s01"}]}]}
    (tmp_path / "film-spec.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert _load_spec(tmp_path) == payload


def test_iter_shots_skips_malformed() -> None:
    spec = {
        "scenes": [
            "bad",
            {
                "shots": [
                    {"id": "s01", "prompt": "a"},
                    "nope",
                    {"prompt": "no id"},
                    {"id": "s02"},
                ]
            },
        ]
    }
    shots = _iter_shots(spec)
    assert [s["id"] for s in shots] == ["s01", "s02"]


def test_iter_shots_empty_scenes() -> None:
    assert _iter_shots({}) == []
    assert _iter_shots({"scenes": []}) == []
