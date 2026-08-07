"""H3 native XOR chain — unit cover for stages_tts_stems / native_audio lane."""

from __future__ import annotations

from final.native_audio import (
    FILM_NATIVE_STABLE_BASENAME,
    NATIVE_LIGHT_AF_FILTER,
    dialogue_lane_suppresses_native,
    dialogue_lane_tts_mix_gain,
    resolve_dialogue_audio_lane,
)
from final.stages_dual_mix import dialogue_xor_violations


def test_native_light_filter_has_no_agate_or_dual_arnndn() -> None:
    """P0 · H3 原声轻处理：机读禁默认 agate / 双 arnndn。"""
    f = NATIVE_LIGHT_AF_FILTER
    assert "highpass" in f and "afftdn" in f and "loudnorm" in f
    assert "agate" not in f
    assert f.count("arnndn") == 0
    assert FILM_NATIVE_STABLE_BASENAME.startswith("film_native_stable")


def test_prefer_native_lane_when_stem_present() -> None:
    shot = {"id": "s1", "audio_policy": "prefer_native"}
    lane = resolve_dialogue_audio_lane(
        shot,
        has_native_stem=True,
        native_audible=True,
        has_spoken_text=True,
        audio_policy="prefer_native",
    )
    assert lane == "native"
    assert dialogue_lane_tts_mix_gain(lane) == 0.0
    assert dialogue_lane_suppresses_native(lane) is False


def test_post_tts_suppresses_native() -> None:
    shot = {"id": "s2", "dialogue_audio_lane": "post_tts"}
    lane = resolve_dialogue_audio_lane(
        shot,
        has_native_stem=True,
        native_audible=True,
        has_spoken_text=True,
    )
    assert lane == "post_tts"
    assert dialogue_lane_suppresses_native(lane) is True
    assert dialogue_lane_tts_mix_gain(lane) > 0


def test_xor_bookkeeping_blocks_double_speak() -> None:
    bad = [
        {
            "id": "bad",
            "dialogue_audio_lane": "native",
            "tts_mix_gain": 0.9,
        }
    ]
    assert dialogue_xor_violations(bad) == ["bad"]
    good = [
        {
            "id": "ok",
            "dialogue_audio_lane": "native",
            "tts_mix_gain": 0.0,
            "caption_clock_only": True,
        }
    ]
    assert dialogue_xor_violations(good) == []
