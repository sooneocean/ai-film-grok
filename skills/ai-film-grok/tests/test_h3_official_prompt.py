"""Official MiniMax H3 prompt dialect + auto policy (O3 canary)."""

from __future__ import annotations

from typing import Any

import pytest

from h3_official_prompt import (
    compile_official_h3_prompt,
    map_official_mode,
    resolve_prompt_dialect,
    validate_official_prompt,
)


def _dlg_shot() -> dict[str, Any]:
    return {
        "id": "s_dlg",
        "dramatic_function": "dialogue",
        "shot_size": "cu",
        "duration_sec": 5.0,
        "dsl": {
            "action": "jaw opens on each Mandarin syllable",
            "camera_prompt": "locked ECU",
            "subject": "young woman",
            "style": "cel-anime",
            "prompt_tier": "medium",
        },
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "过来，靠近一点，别停。",
                "screen_mode": "on_camera",
            }
        ],
    }


def _hi_shot() -> dict[str, Any]:
    return {
        "id": "s_hi",
        "dramatic_function": "action",
        "heat_phase": "act",
        "shot_size": "ms",
        "duration_sec": 5.0,
        "dsl": {
            "action": "full-body weight shifts and torso torque",
            "motion": "hands re-grip",
            "visible_change": "pose silhouette changes every half second",
            "camera_prompt": "aggressive handheld push-in",
            "subject": "athletic woman",
            "style": "cel anime",
            "prompt_tier": "high",
        },
        "prompt_tier": "high",
    }


def test_map_modes() -> None:
    assert map_official_mode("i2v") == "I2VA"
    assert map_official_mode("flf") == "FL2VA"
    assert map_official_mode("r2v") == "Ref2VA"
    assert map_official_mode("t2v") == "T2VA"


def test_force_official_and_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_H3_PROMPT_DIALECT", "official")
    assert resolve_prompt_dialect({}) == "official"
    monkeypatch.setenv("AIFILM_H3_PROMPT_DIALECT", "legacy")
    assert resolve_prompt_dialect({}) == "legacy"
    assert resolve_prompt_dialect({"dsl": {"prompt_format": "timeline"}}) == "legacy"


def test_auto_dialogue_official_high_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_H3_PROMPT_DIALECT", "auto")
    assert resolve_prompt_dialect(_dlg_shot()) == "official"
    assert resolve_prompt_dialect(_hi_shot()) == "legacy"
    soft = {
        "id": "s",
        "dsl": {"action": "soft blink", "prompt_tier": "soft", "style": "cel"},
        "prompt_tier": "soft",
    }
    assert resolve_prompt_dialect(soft) == "official"


def test_i2va_fields_and_dialogue_tag() -> None:
    text = compile_official_h3_prompt(_dlg_shot(), mode="i2v", duration_sec=5.0)
    assert "integrated_multimodal_description:" in text
    assert "overall_soundscape:" in text
    assert "non_diegetic_music:" in text
    assert "<Picture 1>" in text
    assert "<d>[Mandarin] 过来，靠近一点，别停。</d>" in text
    assert "(S1)" in text
    assert "[0s-" not in text
    assert validate_official_prompt(text, mode="i2v")["ok"] is True


def test_high_motion_densifies_action() -> None:
    text = compile_official_h3_prompt(_hi_shot(), mode="i2v", duration_sec=5.0)
    assert "half-second" in text or "HIGH-ENERGY" in text or "inertia" in text
    assert "shakes strongly" in text or "large amplitude" in text
    assert validate_official_prompt(text, mode="i2v")["ok"] is True


def test_ref2va_sections() -> None:
    text = compile_official_h3_prompt(_hi_shot(), mode="r2v")
    for k in (
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ):
        assert k in text
    assert validate_official_prompt(text, mode="r2v")["ok"] is True


def test_motion_core_dialogue_survives() -> None:
    from motion_prompt_spine import assert_motion_prompt_core

    shot = _dlg_shot()
    text = compile_official_h3_prompt(shot, mode="i2v")
    assert_motion_prompt_core(text, shot, mode="i2v", role="hero")
