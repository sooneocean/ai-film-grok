from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.film_io import (  # noqa: E402
    director_notes_path,
    empty_manifest,
    ensure_tree,
    film_dirs,
    load_director_notes,
    load_manifest,
    save_director_notes,
    save_manifest,
)
from util.errors import FilmError  # noqa: E402


# --------------------------------------------------------------------------
# empty_manifest
# --------------------------------------------------------------------------
def test_empty_manifest_basic_shape():
    m = empty_manifest(title="T", theme="neo", aspect="9:16")
    assert m["title"] == "T"
    assert m["theme"] == "neo"
    assert m["aspect_ratio"] == "9:16"
    assert isinstance(m["width"], int) and m["width"] > 0
    assert isinstance(m["height"], int) and m["height"] > m["width"]  # portrait 9:16
    for key in (
        "schema_version",
        "provider_default",
        "truth_contract",
        "stills",
        "clips",
        "outputs",
        "notes",
        "gates",
    ):
        assert key in m


def test_empty_manifest_gates_exactly_one_brief():
    gates = empty_manifest(title="T", theme="neo", aspect="9:16")["gates"]
    assert all(isinstance(v, bool) for v in gates.values())
    assert gates.get("brief") is True
    assert sum(1 for v in gates.values() if v) == 1


def test_empty_manifest_timestamps_present():
    m = empty_manifest(title="T", theme="neo", aspect="9:16")
    assert isinstance(m["created_at"], str) and "T" in m["created_at"]
    assert isinstance(m["updated_at"], str) and "T" in m["updated_at"]


# --------------------------------------------------------------------------
# film_dirs / ensure_tree
# --------------------------------------------------------------------------
def test_ensure_tree_creates_expected_subdirs(tmp_path):
    ensure_tree(tmp_path)
    dirs = film_dirs(tmp_path)
    assert dirs["root"] == tmp_path
    for name in ("prompts", "canonical", "keyframes", "clips", "audio", "out", "receipts"):
        assert name in dirs
        assert dirs[name].is_dir()
        assert str(dirs[name]).startswith(str(tmp_path))


# --------------------------------------------------------------------------
# manifest round-trip
# --------------------------------------------------------------------------
def test_manifest_save_load_roundtrip(tmp_path):
    m = empty_manifest(title="T", theme="neo", aspect="9:16")
    save_manifest(tmp_path, m)
    loaded = load_manifest(tmp_path)
    assert loaded["title"] == "T"
    assert loaded["aspect_ratio"] == "9:16"


def test_load_manifest_missing_raises(tmp_path):
    with pytest.raises(FilmError):
        load_manifest(tmp_path)


# --------------------------------------------------------------------------
# director notes
# --------------------------------------------------------------------------
def test_director_notes_path_is_director_notes_json(tmp_path):
    assert director_notes_path(tmp_path).name == "director_notes.json"


def test_director_notes_save_load_roundtrip(tmp_path):
    notes = {"a": 1, "b": [2, 3]}
    save_director_notes(tmp_path, notes)
    assert load_director_notes(tmp_path) == notes


def test_load_director_notes_missing_returns_dict(tmp_path):
    assert isinstance(load_director_notes(tmp_path), dict)
