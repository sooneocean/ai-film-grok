"""Wave γ · VO-fit defaults, mid_motion cut_on, tight freeze pad."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    MAX_FREEZE_PAD_NO_LOOP_SEC,
    MAX_FREEZE_PAD_SEC,
    apply_film_edit_rhythm_defaults,
    apply_shot_edit_rhythm_defaults,
    default_cut_on_for_shot,
    default_visual_fit,
    lint_equal_duration_ppt,
    plan_stretch,
    resolve_shot_visual_fit,
    shot_has_spoken_dialogue,
)


def test_freeze_pad_tightened() -> None:
    assert MAX_FREEZE_PAD_SEC <= 0.15 + 1e-9
    assert MAX_FREEZE_PAD_NO_LOOP_SEC <= 0.20 + 1e-9


def test_dialogue_drama_defaults_visual_fit_vo() -> None:
    assert default_visual_fit({"vo_mode": "dialogue_drama"}) == "vo"
    assert default_visual_fit({"visual_fit": "slot", "vo_mode": "dialogue_drama"}) == "slot"
    assert default_visual_fit({}) == "slot"


def test_spoken_dialogue_resolves_vo() -> None:
    shot = {
        "id": "d1",
        "screen_mode": "on_camera",
        "spoken_text": "你先走",
        "duration_sec": 6,
    }
    assert shot_has_spoken_dialogue(shot)
    assert resolve_shot_visual_fit({"visual_fit": "slot"}, shot) == "vo"


def test_drive_cut_on_mid_motion() -> None:
    shot = {"id": "a1", "dramatic_function": "action", "dsl": {"motion": "reaches latch"}}
    assert default_cut_on_for_shot(shot) == "mid_motion"
    notes = apply_shot_edit_rhythm_defaults(shot)
    assert notes["cut_on_applied"] is True
    assert shot["dsl"]["cut_on"] == "mid_motion"


def test_apply_film_sets_visual_fit_for_dialogue_drama() -> None:
    spec = {
        "vo_mode": "dialogue_drama",
        "scenes": [
            {
                "shots": [
                    {
                        "id": "s1",
                        "dramatic_function": "hook",
                        "dsl": {"motion": "opens door hard"},
                    }
                ]
            }
        ],
    }
    rep = apply_film_edit_rhythm_defaults(spec)
    assert spec.get("visual_fit") == "vo"
    assert "visual_fit=vo" in (rep.get("applied") or [])
    assert spec["scenes"][0]["shots"][0]["dsl"].get("cut_on") == "mid_motion"


def test_ppt_lint_flags_equal_six() -> None:
    shots = [{"id": f"s{i}", "duration_sec": 6.0} for i in range(6)]
    rep = lint_equal_duration_ppt(shots, visual_fit="slot")
    assert rep["ok"] is False
    assert "EQUAL_SLOT_PPT_RISK" in (rep.get("codes") or [])
    # vo fit skips
    assert lint_equal_duration_ppt(shots, visual_fit="vo")["ok"] is True


def test_plan_stretch_freeze_cap_tight() -> None:
    plan = plan_stretch(6.0, 6.5, dramatic_function="hook")
    assert plan["freeze_sec"] <= MAX_FREEZE_PAD_NO_LOOP_SEC + 1e-6
    assert plan.get("loops", 0) == 0
