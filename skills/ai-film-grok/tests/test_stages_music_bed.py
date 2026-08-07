"""Unit tests for final.stages_music_bed (W1.2)."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from final.stages_music_bed import apply_plan_mood, resolve_music_seed


def test_apply_plan_mood_override() -> None:
    assert apply_plan_mood("rnb", {"mood": "dark"}) == "dark"
    assert apply_plan_mood("rnb", {}) == "rnb"
    assert apply_plan_mood("rnb", None) == "rnb"


def test_resolve_music_seed_cli_wins() -> None:
    args = SimpleNamespace(music_seed=42)
    seed, ap, mood = resolve_music_seed(
        args=args,
        spec={"audio_policy": {"music_seed": 7}, "title": "t"},
        root=Path("/tmp/film"),
        mood="rnb",
        total_dur=12.0,
    )
    assert seed == 42
    assert mood == "rnb"
    assert ap.get("music_seed") == 7


def test_resolve_music_seed_policy_then_stable_hash() -> None:
    args = SimpleNamespace(music_seed=None)
    seed1, _, _ = resolve_music_seed(
        args=args,
        spec={"audio_policy": {"music_seed": 99}, "title": "t"},
        root=Path("/tmp/film"),
        mood="rnb",
        total_dur=12.0,
    )
    assert seed1 == 99
    seed2, _, _ = resolve_music_seed(
        args=args,
        spec={"title": "SameFilm"},
        root=Path("/tmp/film"),
        mood="rnb",
        total_dur=30.0,
    )
    seed3, _, _ = resolve_music_seed(
        args=args,
        spec={"title": "SameFilm"},
        root=Path("/tmp/film"),
        mood="rnb",
        total_dur=30.0,
    )
    assert seed2 == seed3
