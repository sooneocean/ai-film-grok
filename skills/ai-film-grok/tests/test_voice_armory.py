from __future__ import annotations

from voice_armory import catalog, get_voice_profile, ready_tts_profile


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


def test_reference_profiles_are_catalogued_but_never_silently_rendered() -> None:
    assert ready_tts_profile("higgs_zh_female_reference") is None
    assert get_voice_profile("qwen_zh_female_clone")["status"].startswith("needs_")
    assert "qwen_zh_female_design" in catalog()
