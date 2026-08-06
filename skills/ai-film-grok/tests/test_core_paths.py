from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.paths import (  # noqa: E402
    film_output_path,
    record_file_matches,
    valid_shot_id,
)
from util.errors import FilmError  # noqa: E402


# --------------------------------------------------------------------------
# valid_shot_id
# --------------------------------------------------------------------------
def test_valid_shot_id_accepts_pattern():
    assert valid_shot_id("s01") == "s01"
    assert valid_shot_id("Shot-1_a") == "Shot-1_a"
    assert valid_shot_id("A" * 64) == "A" * 64  # boundary length


def test_valid_shot_id_rejects_unsafe():
    for bad in ["", " ", "..", "../x", "/etc/passwd", "a b", "a.b", "a" * 65]:
        with pytest.raises(FilmError):
            valid_shot_id(bad)


# --------------------------------------------------------------------------
# film_output_path
# --------------------------------------------------------------------------
def test_film_output_path_builds_out_mp4(tmp_path):
    p = film_output_path(tmp_path, "final.mp4")
    assert p == tmp_path / "out" / "final.mp4"
    assert p.suffix == ".mp4"


def test_film_output_path_rejects_bad_suffix(tmp_path):
    with pytest.raises(FilmError):
        film_output_path(tmp_path, "final.exe")


def test_film_output_path_rejects_path_traversal(tmp_path):
    with pytest.raises(FilmError):
        film_output_path(tmp_path, "../escape.mp4")


def test_film_output_path_rejects_abs_path(tmp_path):
    with pytest.raises(FilmError):
        film_output_path(tmp_path, "/tmp/final.mp4")


# --------------------------------------------------------------------------
# record_file_matches
# --------------------------------------------------------------------------
def _write(tmp_path: Path, name: str, data: bytes = b"payload") -> Path:
    f = tmp_path / name
    f.write_bytes(data)
    return f


def test_record_file_matches_true_when_sha_matches(tmp_path):
    _write(tmp_path, "a.mp4", b"payload")
    digest = hashlib.sha256(b"payload").hexdigest()
    rec = {"path": "a.mp4", "sha256": digest}
    assert record_file_matches(tmp_path, rec, field="record") is True


def test_record_file_matches_false_on_wrong_sha(tmp_path):
    _write(tmp_path, "a.mp4", b"payload")
    rec = {"path": "a.mp4", "sha256": "0" * 64}
    assert record_file_matches(tmp_path, rec, field="record") is False


def test_record_file_matches_false_on_missing_file(tmp_path):
    rec = {"path": "nope.mp4", "sha256": "0" * 64}
    assert record_file_matches(tmp_path, rec, field="record") is False


def test_record_file_matches_false_on_empty_sha(tmp_path):
    _write(tmp_path, "a.mp4", b"payload")
    assert record_file_matches(tmp_path, {"path": "a.mp4", "sha256": ""}, field="record") is False
    assert record_file_matches(tmp_path, {"path": "a.mp4"}, field="record") is False


def test_record_file_matches_false_on_bad_record():
    assert record_file_matches(None, {"no_path": 1}, field="record") is False
    assert record_file_matches(None, "notadict", field="record") is False
    assert record_file_matches(None, None, field="record") is False
