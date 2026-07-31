from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dialogue_production_plan as plan_module  # noqa: E402
from aifilm_grok import cmd_dialogue_production_plan  # noqa: E402
from dialogue_production_plan import build_dialogue_production_plan  # noqa: E402
from story_plan import run_plan  # noqa: E402
from util import write_json  # noqa: E402


def test_plan_binds_all_weapons_to_one_line_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plan_module, "validate_film_spec", lambda spec, **kwargs: spec)
    package = {
        "schema_version": 1,
        "kind": "dialogue-scene-package",
        "mode": "dialogue_drama",
        "scenes": [
            {
                "scene_id": "sc01",
                "lines": [
                    {
                        "line_id": "sc01_ln01",
                        "speaker": "hero",
                        "spoken_text": "行く。",
                        "caption_text": "我要走。",
                        "emotion": "决绝",
                        "subtext": "反击",
                        "action_while_speaking": "抬眼",
                        "listener": "partner",
                        "scene_state_id": "s1",
                        "screen_mode": "on_camera",
                        "lipsync_required": True,
                        "audio": {"status": "measured", "duration_sec": 1.0},
                    }
                ],
            }
        ],
    }
    write_json(
        tmp_path / "film-spec.json",
        {
            "vo_mode": "dialogue_drama",
            "scenes": [{"shots": [{"id": "sh01", "dialogue_line_id": "sc01_ln01"}]}],
        },
    )
    write_json(tmp_path / "dialogue-scene-package.json", package)
    plan = build_dialogue_production_plan(tmp_path)
    assert (tmp_path / "dialogue-production-plan.json").is_file()
    assert [stage["tool"] for stage in plan["stages"]] == [
        "character_voice_lock_and_audio_timeline",
        "comfy_qwen_i2i_performance_state",
        "comfy_qwen_i2i_keyframe",
        "frw_upload_image",
        "frw_ltx23_img2video_audio",
        "visual-text-audit",
        "visual-text-repair",
        "native_text_gate.validate_native_text_review",
        "frw_img2video",
        "rtx_latentsync_1_6",
        "mmaudio_or_audio_node_with_foley_plan",
    ]
    assert {stage["line_id"] for stage in plan["stages"]} == {"sc01_ln01"}
    fallback = next(stage for stage in plan["stages"] if stage["tool"] == "rtx_latentsync_1_6")
    assert fallback["activation"].startswith("only_after_ltx_native_audio_rejection")
    frw_fallback = next(stage for stage in plan["stages"] if stage["tool"] == "frw_img2video")
    assert frw_fallback["activation"].startswith("only_after_ltx_native_audio_rejection")
    assert frw_fallback["depends_on"] == [
        "sc01_ln01:frw-keyframe-upload",
        "sc01_ln01:native-text-gate",
    ]
    upload = next(stage for stage in plan["stages"] if stage["tool"] == "frw_upload_image")
    assert upload["depends_on"] == ["sc01_ln01:keyframe"]
    assert fallback["depends_on"] == [frw_fallback["stage_id"], "sc01_ln01:tts"]
    native_text = next(
        stage
        for stage in plan["stages"]
        if stage["tool"] == "native_text_gate.validate_native_text_review"
    )
    assert native_text["depends_on"] == [
        "sc01_ln01:visual-text-audit",
        "sc01_ln01:visual-text-repair",
    ]
    assert plan["route"]["lipsync_primary"] == "frw_ltx23_native_audio_i2v_human_verified"
    assert plan["route"]["dialogue_i2v_fallback"] == "frw_img2video_rejection_only"
    assert "caption_owner_ffmpeg_or_hyperframes_once" in plan["post"]["evidence_required"]
    assert "dialogue_route_acceptance" in plan["post"]["evidence_required"]


def test_plan_refuses_a_film_spec_rejected_by_canonical_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_json(tmp_path / "film-spec.json", {"vo_mode": "dialogue_drama"})
    write_json(
        tmp_path / "dialogue-scene-package.json",
        {
            "schema_version": 1,
            "kind": "dialogue-scene-package",
            "mode": "dialogue_drama",
            "scenes": [],
        },
    )

    def reject(*_args: object, **_kwargs: object) -> None:
        raise plan_module.FilmSpecError("missing beat coverage")

    monkeypatch.setattr(plan_module, "validate_film_spec", reject)
    with pytest.raises(ValueError, match="FILM_SPEC_INVALID"):
        build_dialogue_production_plan(tmp_path)


def test_cli_reports_invalid_film_spec_without_traceback(tmp_path: Path, capsys) -> None:
    write_json(tmp_path / "film-spec.json", {"scenes": []})

    assert cmd_dialogue_production_plan(Namespace(root=str(tmp_path))) == 2

    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "status": "blocked",
        "reason": "DIALOGUE_PRODUCTION_PLAN_FILM_SPEC_INVALID",
    }


def test_plan_rejects_one_missing_beat_coverage_from_real_projection(tmp_path: Path) -> None:
    run_plan(tmp_path, "阿澄：你为什么还没下车？\n乘客：因为照片背后写着你的名字。", force=True)
    spec_path = tmp_path / "film-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    speaking = [
        shot
        for scene in spec["scenes"]
        for shot in scene["shots"]
        if shot.get("screen_mode") == "on_camera"
    ]
    for shot, japanese in zip(
        speaking, ("まだ降りないの？", "写真の裏に君の名前がある。"), strict=True
    ):
        shot["dialogue_ja"] = japanese
        shot["dialogue"] = japanese
        shot["translation_status"] = "ready"
        shot["audio_cues"][0].update(spoken_text=japanese, translation_status="ready")
    spec.update(heat_arc_strict=False, adult_max_iron=False)
    removed_beat = speaking[0].get("beat_id") or speaking[0].get("dialogue_line_id")
    for scene in spec["scenes"]:
        scene["shots"] = [
            shot
            for shot in scene["shots"]
            if not (
                shot.get("screen_mode") in {"reaction", "action_cover", "silence"}
                and shot.get("beat_id") == removed_beat
            )
        ]
    write_json(spec_path, spec)
    with pytest.raises(ValueError, match="FILM_SPEC_INVALID"):
        build_dialogue_production_plan(tmp_path)
