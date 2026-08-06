"""1:1 test for audio.ltx23_audio_canary (P3-1 migration + contract lock).

Migrated from scripts/ltx23_audio_canary.py into the audio package. These
tests pin the public contract so future refactors of the compile step are
caught.
"""
from __future__ import annotations

import pytest

from audio.ltx23_audio_canary import compile_audio_conditioned_workflow


def _valid() -> dict:
    return compile_audio_conditioned_workflow(
        image_name="img.png",
        audio_name="voice.wav",
        prompt="a serene lake",
        seed=12345,
        frames=81,
        filename_prefix="pilot",
    )


def test_rejects_missing_required_fields():
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="", audio_name="v.wav", prompt="p", seed=1, frames=81, filename_prefix="x"
        )
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="i.png", audio_name="", prompt="p", seed=1, frames=81, filename_prefix="x"
        )
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="i.png", audio_name="v.wav", prompt="p", seed=1, frames=81, filename_prefix=""
        )


def test_rejects_frames_out_of_range_and_bad_step():
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="i.png", audio_name="v.wav", prompt="p", seed=1, frames=8, filename_prefix="x"
        )
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="i.png", audio_name="v.wav", prompt="p", seed=1, frames=250, filename_prefix="x"
        )
    # 10 is not 8n+1
    with pytest.raises(ValueError):
        compile_audio_conditioned_workflow(
            image_name="i.png", audio_name="v.wav", prompt="p", seed=1, frames=10, filename_prefix="x"
        )


def test_binds_inputs_into_template_graph():
    g = _valid()
    assert g["source"]["inputs"]["image"] == "img.png"
    assert g["303"]["inputs"]["text"] == "a serene lake"
    assert g["277"]["inputs"]["noise_seed"] == 12345
    assert g["save"]["inputs"]["filename_prefix"] == "pilot"
    assert g["295"]["inputs"]["length"] == 81
    assert g["305"]["inputs"]["frames_number"] == 81


def test_injects_audio_latent_chain():
    g = _valid()
    assert g["audio_source"] == {"class_type": "LoadAudio", "inputs": {"audio": "voice.wav"}}
    assert g["audio_encode"]["class_type"] == "LTXVAudioVAEEncode"
    assert g["audio_encode"]["inputs"]["audio"] == ["audio_source", 0]
    assert g["audio_encode"]["inputs"]["audio_vae"] == ["279", 0]
    assert g["318"]["inputs"]["audio_latent"] == ["audio_encode", 0]
