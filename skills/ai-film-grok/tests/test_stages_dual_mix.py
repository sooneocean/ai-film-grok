"""Unit tests for final.stages_dual_mix pure policy leaves (W1)."""

from __future__ import annotations

import os

import pytest

from final.stages_dual_mix import (
    apply_mix_path_env_policy,
    dialogue_xor_violations,
)


@pytest.fixture(autouse=True)
def _clear_mix_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "AIFILM_FORCE_SIMPLE_AMIX",
        "AIFILM_ALLOW_ACROSSOVER_MIX",
        "AIFILM_FORCE_BROADBAND_DUCK",
    ):
        monkeypatch.delenv(key, raising=False)


def test_mix_path_default_broadband_strips_acrossover() -> None:
    spotting: dict = {}
    out = apply_mix_path_env_policy(
        "sidechaincompress acrossover other",
        mix_spotting=spotting,
    )
    assert " acrossover " not in f" {out} "
    assert "___disabled_acrossover___" in out
    assert spotting.get("mix_path") == "broadband_default"
    assert spotting.get("force_broadband_duck") is True


def test_mix_path_force_simple_amix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_FORCE_SIMPLE_AMIX", "1")
    spotting: dict = {}
    out = apply_mix_path_env_policy("sidechaincompress acrossover", mix_spotting=spotting)
    assert out == ""
    assert spotting.get("mix_path") == "simple_amix"


def test_mix_path_allow_acrossover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_ALLOW_ACROSSOVER_MIX", "true")
    spotting: dict = {}
    help_text = "sidechaincompress acrossover"
    out = apply_mix_path_env_policy(help_text, mix_spotting=spotting)
    assert out == help_text
    assert spotting.get("mix_path") == "acrossover_multiband"


def test_dialogue_xor_native_with_tts_gain() -> None:
    shots = [
        {"id": "s1", "dialogue_audio_lane": "native", "tts_mix_gain": 0.8},
        {"id": "s2", "dialogue_audio_lane": "native", "tts_mix_gain": 0.0},
    ]
    assert dialogue_xor_violations(shots) == ["s1"]


def test_dialogue_xor_post_tts_with_native_audible() -> None:
    shots = [
        {
            "id": "s3",
            "dialogue_audio_lane": "post_tts",
            "native_audio": {"path": "x.wav"},
            "native_audio_suppressed_for_tts": False,
            "native_audio_audible": True,
        }
    ]
    assert dialogue_xor_violations(shots) == ["s3"]
