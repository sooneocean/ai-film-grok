"""H3/native-primary dialogue stem plans (W1.5). Edge TTS is escape only."""

from __future__ import annotations

from final.stages_dialogue_stems import plan_dialogue_stem, resolve_film_audio_policy


def test_h3_native_preferred_when_stem_present() -> None:
    plan = plan_dialogue_stem(
        {"id": "s1"},
        has_native_stem=True,
        native_audible=True,
        spoken_text="你好",
        non_vo_coverage=False,
        film_audio_policy="prefer_native",
    )
    assert plan.lane == "native"
    assert plan.needs_edge_tts is False
    assert plan.tts_mix_gain == 0.0
    assert plan.caption_clock_only is True
    assert plan.note == "native_xor_caption_clock"


def test_edge_only_when_force_strip_policy() -> None:
    plan = plan_dialogue_stem(
        {"id": "s1", "audio_policy": "strip_native_use_tts_bgm"},
        has_native_stem=True,
        native_audible=True,
        spoken_text="你好",
        non_vo_coverage=False,
    )
    assert plan.lane == "post_tts"
    assert plan.needs_edge_tts is True
    assert plan.tts_mix_gain == 1.0


def test_no_edge_without_spoken_even_on_strip() -> None:
    plan = plan_dialogue_stem(
        {"id": "s1", "audio_policy": "strip_native_use_tts_bgm"},
        has_native_stem=True,
        native_audible=True,
        spoken_text="",
        non_vo_coverage=False,
    )
    assert plan.needs_edge_tts is False


def test_resolve_film_audio_policy() -> None:
    assert resolve_film_audio_policy({"audio_policy": {"mode": "prefer_native"}}) == "prefer_native"
