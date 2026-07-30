from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dialogue_production_plan as plan_module  # noqa: E402
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
        "comfy_wan22_i2v",
        "rtx_latentsync_1_6",
        "mmaudio_or_audio_node_with_foley_plan",
    ]
    assert {stage["line_id"] for stage in plan["stages"]} == {"sc01_ln01"}


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
