"""W1.8 orchestration leaves import + export smoke."""

from __future__ import annotations


def test_voice_timeline_export() -> None:
    from final.stages_voice_timeline import build_narration_and_native_tracks

    assert callable(build_narration_and_native_tracks)


def test_audio_prep_export() -> None:
    from final.stages_audio_prep import prepare_audio_mix_context

    assert callable(prepare_audio_mix_context)


def test_dual_mix_stage_export() -> None:
    from final.stages_dual_mix import run_dual_track_mix_stage

    assert callable(run_dual_track_mix_stage)


def test_delivery_report_export() -> None:
    from final.stages_delivery_report import write_technical_delivery

    assert callable(write_technical_delivery)


def test_render_final_is_orchestrator_shaped() -> None:
    from pathlib import Path
    import ast

    src = (Path(__file__).resolve().parents[1] / "scripts/post/render_final.py").read_text()
    tree = ast.parse(src)
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == "render_final":
            span = n.end_lineno - n.lineno + 1
            # W1.8 direction: well under 800 after peels (target later <400)
            assert span < 800, f"render_final still too thick: {span}"
            return
    raise AssertionError("render_final missing")
