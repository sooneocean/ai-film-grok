"""Tests for render_final pure helpers (P1, senior-dev quality plan).

First extraction from the 2454-line ``render_final`` monolith: a self-contained,
side-effect-free dimension resolver. This is the reference pattern for chipping
away the giant function — extract a pure, unit-tested helper, then call it.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def render_final_mod():
    mod = importlib.import_module("render_final")
    return mod


def test_resolve_render_dimension_cli_wins(render_final_mod) -> None:
    assert (
        render_final_mod.resolve_render_dimension(1920, 1280, 720, default=720)
        == 1920
    )


def test_resolve_render_dimension_falls_through_sources(render_final_mod) -> None:
    # CLI empty → timeline → manifest → default
    assert (
        render_final_mod.resolve_render_dimension("", None, 1080, default=720) == 1080
    )
    assert (
        render_final_mod.resolve_render_dimension(None, None, None, default=720) == 720
    )


def test_resolve_render_dimension_skips_non_numeric(render_final_mod) -> None:
    # A non-numeric manifest value must degrade, not raise mid-render.
    assert (
        render_final_mod.resolve_render_dimension("bad", "1080", default=720) == 1080
    )


def test_resolve_render_dimension_zero_is_falsy_source(render_final_mod) -> None:
    # 0 is treated as "not provided" so the next fallback applies.
    assert (
        render_final_mod.resolve_render_dimension(0, 1280, default=720) == 1280
    )


def test_resolve_plate_slot_sec_from_shot(render_final_mod) -> None:
    assert render_final_mod.resolve_plate_slot_sec({"duration_sec": 5.0}) == 5.0
    assert render_final_mod.resolve_plate_slot_sec({"duration_sec": 0.0}) == 1.0
    assert render_final_mod.resolve_plate_slot_sec({"duration_sec": 0.01}) == 1.0
    assert render_final_mod.resolve_plate_slot_sec({}) == 1.0
    assert render_final_mod.resolve_plate_slot_sec({"duration_sec": "bad"}) == 1.0
    assert (
        render_final_mod.resolve_plate_slot_sec(
            {"duration_sec": 0.0}, default=2.5
        )
        == 2.5
    )


def test_resolve_plate_slot_sec_zero_default_keeps_zero(render_final_mod) -> None:
    # cue/slot paths: invalid → 0, not silence-path default 1.0
    assert (
        render_final_mod.resolve_plate_slot_sec({}, default=0.0, min_sec=0.0) == 0.0
    )
    assert (
        render_final_mod.resolve_plate_slot_sec(
            {"duration_sec": "x"}, default=0.0, min_sec=0.0
        )
        == 0.0
    )
    assert (
        render_final_mod.resolve_plate_slot_sec(
            {"duration_sec": 3.25}, default=0.0, min_sec=0.0
        )
        == 3.25
    )

