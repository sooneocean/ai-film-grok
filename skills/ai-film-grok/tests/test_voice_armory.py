from __future__ import annotations

import pytest
from voice_armory import (
    catalog,
    get_voice_profile,
    ready_tts_profile,
    render_ready_tts_profile,
    tts_model_catalog,
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
    assert get_voice_profile("qwen_zh_female_clone")["status"] == "needs_authorized_reference"
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


def test_chinese_male_design_presets_require_a_decoded_audio_canary() -> None:
    for profile_id in ("qwen_zh_male_narrator", "qwen_zh_male_warm"):
        profile = get_voice_profile(profile_id)
        assert profile is not None
        assert profile["language"] == "Chinese"
        assert profile["variant"] == "voice_design"
        assert profile["status"] == "candidate_canary_pending"
        assert ready_tts_profile(profile_id) is None
        assert "非固定角色" in profile["label"]


def test_node_voice_resolution_rejects_unknown_or_unavailable_variants() -> None:
    with pytest.raises(ValueError, match="unknown voice profile"):
        render_ready_tts_profile("unregistered_profile", {"voice_design": True})
    with pytest.raises(ValueError, match="variant is unavailable"):
        render_ready_tts_profile("qwen_zh_female_vivian", {"custom_1_7b": False})


def test_node_voice_resolution_uses_only_live_catalogued_variant() -> None:
    profile = render_ready_tts_profile("qwen_zh_female_vivian", {"custom_1_7b": True})
    assert profile["speaker"] == "Vivian"


def test_fast_and_multilingual_profiles_require_the_small_custom_variant() -> None:
    for profile_id in (
        "qwen_zh_female_vivian_fast",
        "qwen_zh_female_serena_fast",
        "qwen_ja_female_ono_anna",
        "qwen_ko_female_sohee",
    ):
        profile = get_voice_profile(profile_id)
        assert profile is not None
        assert profile["variant"] == "custom_0_6b"
        assert profile["status"] == "requires_node_variant"


def test_multilingual_design_profiles_are_explicitly_bound_to_their_language() -> None:
    expected_languages = {
        "qwen_en_female_design": "English",
        "qwen_en_female_warm": "English",
        "qwen_en_female_confident": "English",
        "qwen_en_female_storyteller": "English",
        "qwen_ja_female_gentle": "Japanese",
        "qwen_ja_female_cool": "Japanese",
        "qwen_ko_female_gentle": "Korean",
        "qwen_ko_female_confident": "Korean",
    }
    for profile_id, language in expected_languages.items():
        profile = ready_tts_profile(profile_id)
        assert profile is not None
        assert profile["language"] == language
        assert profile["variant"] == "voice_design"


def test_japanese_male_design_presets_require_a_decoded_audio_canary() -> None:
    for profile_id in ("qwen_ja_male_gentle", "qwen_ja_male_cool"):
        profile = get_voice_profile(profile_id)
        assert profile is not None
        assert profile["language"] == "Japanese"
        assert profile["status"] == "candidate_canary_pending"
        assert ready_tts_profile(profile_id) is None


def test_tts_model_armory_keeps_unverified_models_non_routable() -> None:
    models = tts_model_catalog()
    assert models["qwen3_tts_5090"]["production_eligible"] is True
    for model_id in (
        "cosyvoice3_local",
        "kokoro_82m_zh",
        "higgs_audio_v2_5",
        "f5_tts",
        "index_tts2",
    ):
        assert models[model_id]["production_eligible"] is False
