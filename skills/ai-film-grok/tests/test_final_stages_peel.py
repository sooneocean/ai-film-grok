"""Unit tests for orchestrator-relief final stage leaves (W1)."""
from __future__ import annotations
from pathlib import Path
from final.render_helpers import coerce_optional_float, resolve_plate_slot_sec, resolve_render_dimension
from final.stages_dual_mix import apply_mix_path_env_policy, dialogue_xor_violations
from final.stages_mux_manifest import mux_final_mp4, verify_final_streams

def test_render_helpers_dimension_and_plate() -> None:
    assert resolve_render_dimension(1920, 720, default=480) == 1920
    assert resolve_plate_slot_sec({"duration_sec": 4.5}) == 4.5
    assert coerce_optional_float(None) is None

def test_dialogue_xor_violations_empty_and_native_tts() -> None:
    assert dialogue_xor_violations([]) == []
    assert dialogue_xor_violations([{"id": "s1", "dialogue_audio_lane": "native", "tts_mix_gain": 0.5}]) == ["s1"]

def test_mix_path_env_default_disables_acrossover_token(monkeypatch) -> None:
    monkeypatch.delenv("AIFILM_FORCE_SIMPLE_AMIX", raising=False)
    monkeypatch.delenv("AIFILM_ALLOW_ACROSSOVER_MIX", raising=False)
    spotting: dict = {}
    out = apply_mix_path_env_policy("acrossover,sidechaincompress", mix_spotting=spotting)
    assert "___disabled_acrossover___" in out
    assert spotting.get("mix_path") == "broadband_default"

def test_mix_path_force_simple_amix(monkeypatch) -> None:
    monkeypatch.setenv("AIFILM_FORCE_SIMPLE_AMIX", "1")
    spotting: dict = {}
    assert apply_mix_path_env_policy("acrossover,foo", mix_spotting=spotting) == ""
    assert spotting.get("mix_path") == "simple_amix"

def test_mux_final_mp4_builds_cmd() -> None:
    seen: list = []
    mux_final_mp4(video_subbed="/v.mp4", mixed="/m.wav", final_path="/out.mp4", run=lambda c, **k: seen.append(c))
    assert seen and seen[0][0] == "ffmpeg"

def test_verify_final_streams_requires_av() -> None:
    class _R: stdout = '{"streams":[{"codec_type":"video"}]}'
    class Err(Exception): pass
    try:
        verify_final_streams(final_path="/f.mp4", audio_timeline_v1=False, run=lambda *a, **k: _R(), render_error_cls=Err)
        raise AssertionError("expected")
    except Err as e:
        assert "missing" in str(e).lower()

def test_render_context_module_exports() -> None:
    from final.render_context import RenderContext, load_render_context
    assert callable(load_render_context)
