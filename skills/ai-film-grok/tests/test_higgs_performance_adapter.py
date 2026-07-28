from __future__ import annotations

from adapters.higgs_performance import _max_new_tokens, _system_prompt


def test_higgs_performance_prompt_excludes_speech_and_music() -> None:
    prompt = _system_prompt("a brief breathy startled reaction")
    assert "<|scene_desc_start|>" in prompt
    assert "<|scene_desc_end|>" in prompt
    assert "No intelligible words" in prompt
    assert "no singing" in prompt
    assert "no music" in prompt
    assert "a brief breathy startled reaction" in prompt


def test_higgs_performance_token_budget_is_bounded() -> None:
    assert _max_new_tokens(1) == 64
    assert _max_new_tokens(10) == 500
    assert _max_new_tokens(60) == 2048
