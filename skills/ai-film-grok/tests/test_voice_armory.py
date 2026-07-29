from __future__ import annotations

import pytest
from voice_armory import (
    catalog,
    get_voice_profile,
    ready_tts_profile,
    render_ready_tts_profile,
)


def test_ready_chinese_female_profiles_are_explicit_and_stable() -> None:
    for profile_id, speaker in (
        ("qwen_zh_female_vivian", "Vivian"),
        ("qwen_zh_female_serena", "Serena"),
    ):
        profile = ready_tts_profile(profile_id)
        assert profile is not None
        assert profile["variant"] == "custom_1_7b"
        assert profile["speaker"] == speaker
        assert profile["language"] == "Chinese"
        assert profile["status"] == "requires_node_variant"


def test_reference_profiles_are_catalogued_but_never_silently_rendered() -> None:
    assert ready_tts_profile("higgs_zh_female_reference") is None
    assert get_voice_profile("qwen_zh_female_clone")["status"].startswith("needs_")
    assert "qwen_zh_female_design" in catalog()


def test_design_presets_are_ready_but_are_not_presented_as_fixed_characters() -> None:
    for profile_id in (
        "qwen_zh_female_gentle",
        "qwen_zh_female_mature",
        "qwen_zh_female_cool",
        "qwen_zh_female_lively",
        "qwen_zh_female_breathy",
        "qwen_zh_female_narrator",
    ):
        profile = ready_tts_profile(profile_id)
        assert profile is not None
        assert profile["variant"] == "voice_design"
        assert "非固定角色" in profile["label"]


def test_extended_design_presets_are_catalogued_as_chinese_adult_voices() -> None:
    for profile_id in (
        "qwen_zh_female_elegant",
        "qwen_zh_female_husky",
        "qwen_zh_female_whisper",
        "qwen_zh_female_playful",
        "qwen_zh_female_confident",
        "qwen_zh_female_comforting",
        "qwen_zh_female_melancholy",
        "qwen_zh_female_mysterious",
        "qwen_zh_female_documentary",
        "qwen_zh_female_storyteller",
    ):
        profile = ready_tts_profile(profile_id)
        assert profile is not None
        assert profile["language"] == "Chinese"
        assert profile["instruction_prefix"].startswith("成年中文女声")


def test_node_voice_resolution_rejects_unknown_or_unavailable_variants() -> None:
    with pytest.raises(ValueError, match="unknown voice profile"):
        render_ready_tts_profile("unregistered_profile", {"voice_design": True})
    with pytest.raises(ValueError, match="variant is unavailable"):
        render_ready_tts_profile("qwen_zh_female_vivian", {"custom_1_7b": False})


def test_node_voice_resolution_uses_only_live_catalogued_variant() -> None:
    profile = render_ready_tts_profile("qwen_zh_female_vivian", {"custom_1_7b": True})
    assert profile["speaker"] == "Vivian"
