"""Tests for util.validators (P4-1: zero-coverage foundation补漏).

Pure functions only — no filesystem, no GPU, deterministic.
"""
from __future__ import annotations

import pytest
import util.validators as V
from util.errors import FilmError


# --- slugify -----------------------------------------------------------------
def test_slugify_basic_lowercases_and_trims():
    assert V.slugify("  Hello World  ") == "hello-world"


def test_slugify_spaces_underscores_slashes_to_dash():
    assert V.slugify("a b_c/d") == "a-b-c-d"


def test_slugify_collapses_repeated_dashes():
    assert V.slugify("a---b__c") == "a-b-c"


def test_slugify_strips_leading_trailing_dashes():
    assert V.slugify("---hello---") == "hello"


def test_slugify_preserves_cjk():
    assert V.slugify("我的电影 01") == "我的电影-01"


def test_slugify_non_word_chars_dropped():
    # punctuation/emoji are stripped, alphanumerics + CJK kept
    assert V.slugify("Night!@#Scene(2)") == "nightscene2"


def test_slugify_empty_falls_back_to_film():
    assert V.slugify("") == "film"
    assert V.slugify("   ") == "film"
    assert V.slugify("!!!") == "film"


# --- aspect_dims --------------------------------------------------------------
def test_aspect_dims_known_table():
    assert V.aspect_dims("9:16") == (720, 1280)
    assert V.aspect_dims("16:9") == (1280, 720)
    assert V.aspect_dims("1:1") == (1024, 1024)
    assert V.aspect_dims("3:4") == (768, 1024)
    assert V.aspect_dims("4:3") == (1024, 768)


def test_aspect_dims_unknown_raises_filmerror():
    with pytest.raises(FilmError):
        V.aspect_dims("2:1")


def test_aspect_dims_error_message_lists_supported():
    with pytest.raises(FilmError, match="16:9"):
        V.aspect_dims("nonsense")
