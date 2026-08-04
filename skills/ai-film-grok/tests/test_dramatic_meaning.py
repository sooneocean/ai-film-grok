#!/usr/bin/env python3
"""Dramatic meaning gates — shot / motion / dialogue purpose / emotional arc stack."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinematic_audit import audit  # noqa: E402
from continuity import CODE_MOTION_NO_MEANING  # noqa: E402
from dramatic_meaning import (  # noqa: E402
    CODE_ARC_NODE_ORPHAN,
    CODE_ARC_STACK_FLAT,
    CODE_ARC_STACK_NO_MAPPING,
    CODE_DIALOGUE_PURPOSE_EMPTY,
    CODE_DIALOGUE_SPEAKER_MISSING,
    CODE_DIALOGUE_TEXT_EMPTY,
    CODE_SHOT_MEANING_EMPTY,
    lint_dialogue_purpose,
    lint_dramatic_meaning,
    lint_emotional_arc_stack,
    lint_motion_purpose,
    lint_shot_meaning,
    meaning_gate_enabled,
)


def _drive_shot(
    sid: str,
    beat: str,
    *,
    action: str = "steps forward and opens the door",
    motion: str = "hand pulls latch, steps into light, continuous",
    visible_change: str = "door from shut to open; body crosses threshold",
    story_beat: str = "she claims the room",
    arc_node: str | None = None,
    **extra,
) -> dict:
    dsl = {
        "action": action,
        "motion": motion,
        "visible_change": visible_change,
        "story_beat": story_beat,
        "camera": {"shot_size": "medium"},
        "camera_axis": "dolly_in",
    }
    if arc_node is not None:
        dsl["arc_node"] = arc_node
    shot = {
        "id": sid,
        "dramatic_function": beat,
        "shot_role": "hero",
        "performance_delta": visible_change,
        "dsl": dsl,
        "duration_sec": 4,
    }
    shot.update(extra)
    return shot


def _good_arc() -> list[str]:
    return ["好奇登场", "前戏贴近", "进行沉腰", "高潮完成"]


def _good_spec(shots: list[dict], *, heat: str = "max", strict: bool | None = None) -> dict:
    spec: dict = {
        "title": "meaning-gate-fixture",
        "heat_scale": heat,
        "director_intent": {
            "logline": "雨夜后座，一场有意义的靠近。",
            "tone": "成人色气",
            "emotional_arc": _good_arc(),
        },
        "scenes": [{"shots": shots}],
    }
    if strict is not None:
        spec["dramatic_meaning_strict"] = strict
    return spec


def test_shot_meaning_empty_fails():
    shots = [
        {
            "id": "s1",
            "dramatic_function": "hook",
            "dsl": {"motion": "soft blink, slow push-in", "camera": {"shot_size": "medium"}},
        }
    ]
    r = lint_shot_meaning(shots)
    assert not r["ok"]
    assert CODE_SHOT_MEANING_EMPTY in r["codes"]


def test_shot_meaning_with_world_change_passes():
    shots = [_drive_shot("s1", "hook")]
    r = lint_shot_meaning(shots)
    assert r["ok"], r["issues"]
    assert CODE_SHOT_MEANING_EMPTY not in r["codes"]


def test_motion_aesthetic_only_on_drive_beat_fails():
    shots = [
        {
            "id": "s1",
            "dramatic_function": "hook",
            "dsl": {
                "action": "",
                "motion": "soft blink, breath, slow push-in, hair drift, idle not speaking",
                "camera": {"shot_size": "medium"},
            },
        }
    ]
    r = lint_motion_purpose(shots)
    assert not r["ok"]
    assert CODE_MOTION_NO_MEANING in r["codes"] or "BEAT_SEMANTICS_MISS" in r["codes"]


def test_motion_with_beat_serving_change_passes():
    shots = [
        _drive_shot(
            "s1",
            "hook",
            action="pulls curtain and steps into light",
            motion="hand pulls curtain aside, steps forward into vanity light",
            visible_change="from corridor dark into lit dressing room",
            story_beat="she claims the room entrance",
        )
    ]
    r = lint_motion_purpose(shots)
    assert CODE_MOTION_NO_MEANING not in r["codes"]
    assert "BEAT_SEMANTICS_MISS" not in r["codes"]


def test_dialogue_purpose_empty_fails():
    shots = [
        _drive_shot(
            "s1",
            "reaction",
            action="looks back at him",
            motion="eyes glance back, soft look",
            voices=[
                {
                    "speaker": "heroine",
                    "line_type": "dialogue",
                    "spoken_text": "你别过来。",
                }
            ],
        )
    ]
    r = lint_dialogue_purpose(shots)
    assert not r["ok"]
    assert CODE_DIALOGUE_PURPOSE_EMPTY in r["codes"]


def test_dialogue_missing_speaker_fails():
    shots = [
        _drive_shot(
            "s1",
            "reaction",
            action="looks back at him",
            motion="eyes glance back, soft look",
            voices=[
                {
                    "line_type": "dialogue",
                    "spoken_text": "你别过来。",
                    "subtext": "其实想他靠近",
                    "emotion": "guarded",
                }
            ],
        )
    ]
    r = lint_dialogue_purpose(shots)
    assert CODE_DIALOGUE_SPEAKER_MISSING in r["codes"]


def test_dialogue_purpose_bound_passes():
    shots = [
        _drive_shot(
            "s1",
            "reaction",
            action="looks back at him",
            motion="eyes glance back, soft look",
            voices=[
                {
                    "speaker": "heroine",
                    "line_type": "dialogue",
                    "spoken_text": "你别过来。",
                    "subtext": "其实想他再近一点",
                    "emotion": "guarded",
                }
            ],
        )
    ]
    r = lint_dialogue_purpose(shots)
    assert r["ok"], r["issues"]
    assert CODE_DIALOGUE_PURPOSE_EMPTY not in r["codes"]
    assert CODE_DIALOGUE_TEXT_EMPTY not in r["codes"]


def test_arc_stack_flat_fails():
    arc = _good_arc()
    shots = [
        _drive_shot("s1", "hook", arc_node=arc[0]),
        _drive_shot(
            "s2",
            "approach",
            action="leans closer toward him",
            motion="leans close, reaches for his collar",
            arc_node=arc[0],
        ),
        _drive_shot(
            "s3",
            "action",
            action="plants hands on table and leans in",
            motion="plants hands, leans over vanity table",
            arc_node=arc[0],
        ),
    ]
    r = lint_emotional_arc_stack(shots, emotional_arc=arc)
    assert not r["ok"]
    assert CODE_ARC_STACK_FLAT in r["codes"]


def test_arc_orphan_when_enough_shots_fails():
    arc = _good_arc()
    shots = [
        _drive_shot("s1", "hook", arc_node=arc[0]),
        _drive_shot(
            "s2",
            "approach",
            action="leans closer toward him",
            motion="leans close, reaches for his collar",
            arc_node=arc[1],
        ),
        _drive_shot(
            "s3",
            "action",
            action="plants hands on table and leans in",
            motion="plants hands, leans over vanity table",
            arc_node=arc[1],
        ),
        _drive_shot(
            "s4",
            "sensory",
            action="breath rises, sweat bead on collarbone",
            motion="slow breath rise, sweat bead slides",
            arc_node=arc[0],
        ),
    ]
    r = lint_emotional_arc_stack(shots, emotional_arc=arc)
    assert not r["ok"]
    assert CODE_ARC_NODE_ORPHAN in r["codes"]


def test_arc_stack_progression_passes():
    arc = _good_arc()
    shots = [
        _drive_shot("s1", "hook", arc_node=arc[0]),
        _drive_shot(
            "s2",
            "approach",
            action="leans closer toward him",
            motion="leans close, reaches for his collar",
            arc_node=arc[1],
        ),
        _drive_shot(
            "s3",
            "action",
            action="plants hands on table and leans in",
            motion="plants hands, leans over vanity table",
            arc_node=arc[2],
        ),
        _drive_shot(
            "s4",
            "afterglow",
            action="holds residual heat and softens gaze",
            motion="linger hold, soften blink, residual heat",
            arc_node=arc[3],
        ),
    ]
    r = lint_emotional_arc_stack(shots, emotional_arc=arc)
    assert r["ok"], r["issues"]
    assert set(r["covered_indices"]) == {0, 1, 2, 3}


def test_arc_no_mapping_fails():
    shots = [
        {
            "id": "s1",
            "dramatic_function": "",
            "dsl": {"visible_change": "x", "story_beat": "y"},
        }
    ]
    r = lint_emotional_arc_stack(shots, emotional_arc=_good_arc())
    assert CODE_ARC_STACK_NO_MAPPING in r["codes"] or not r["ok"]


def test_composite_good_passes():
    arc = _good_arc()
    shots = [
        _drive_shot("s1", "hook", arc_node=arc[0]),
        _drive_shot(
            "s2",
            "approach",
            action="leans closer toward him",
            motion="leans close, reaches for his collar",
            arc_node=arc[1],
            voices=[
                {
                    "speaker": "heroine",
                    "spoken_text": "坐近点。",
                    "subtext": "试探他敢不敢",
                    "emotion": "teasing",
                }
            ],
        ),
        _drive_shot(
            "s3",
            "action",
            action="plants hands on table and leans in",
            motion="plants hands, leans over vanity table",
            arc_node=arc[2],
        ),
        _drive_shot(
            "s4",
            "afterglow",
            action="holds residual heat and softens gaze",
            motion="linger hold, soften blink, residual heat",
            arc_node=arc[3],
        ),
    ]
    spec = _good_spec(shots, heat="max", strict=True)
    r = lint_dramatic_meaning(spec, shots=shots)
    assert r["ok"], r["issues"]
    assert r["enabled"] is True


def test_composite_bad_aesthetic_and_dialogue_and_flat_arc():
    arc = _good_arc()
    shots = [
        {
            "id": "s1",
            "dramatic_function": "hook",
            "dsl": {
                "motion": "soft blink, breath, slow push-in",
                "arc_node": arc[0],
                "camera": {"shot_size": "medium"},
            },
            "voices": [
                {
                    "speaker": "heroine",
                    "spoken_text": "嗯。",
                }
            ],
        },
        {
            "id": "s2",
            "dramatic_function": "action",
            "dsl": {
                "motion": "gentle breath, idle not speaking",
                "arc_node": arc[0],
                "camera": {"shot_size": "medium"},
            },
        },
    ]
    r = lint_dramatic_meaning(_good_spec(shots), shots=shots)
    assert not r["ok"]
    codes = set(r["codes"])
    assert CODE_SHOT_MEANING_EMPTY in codes or CODE_MOTION_NO_MEANING in codes
    assert CODE_DIALOGUE_PURPOSE_EMPTY in codes
    assert CODE_ARC_STACK_FLAT in codes or CODE_ARC_STACK_NO_MAPPING in codes


def test_meaning_gate_default_on_every_genre():
    """2.37.5: every genre pack fail-closed unless explicit opt-out."""
    import os

    assert meaning_gate_enabled({}) is True
    assert meaning_gate_enabled({"heat_scale": "soft"}) is True
    assert meaning_gate_enabled({"heat_scale": "max"}) is True
    assert meaning_gate_enabled({"quality_target": "premium_vertical"}) is True
    assert meaning_gate_enabled({"heat_scale": "medium", "dramatic_meaning_strict": False}) is False
    assert meaning_gate_enabled({"heat_scale": "medium", "dramatic_meaning_strict": True}) is True
    prev = os.environ.get("AIFILM_SKIP_MEANING_GATE")
    try:
        os.environ["AIFILM_SKIP_MEANING_GATE"] = "1"
        assert meaning_gate_enabled({"heat_scale": "max"}) is False
        assert meaning_gate_enabled({"dramatic_meaning_strict": True}) is True
    finally:
        if prev is None:
            os.environ.pop("AIFILM_SKIP_MEANING_GATE", None)
        else:
            os.environ["AIFILM_SKIP_MEANING_GATE"] = prev


def test_validate_film_spec_hard_fails_on_max_empty_meaning():
    shots = [
        {
            "id": "s1",
            "dramatic_function": "hook",
            "duration_sec": 4,
            "nar": "她走进房间。",
            "dsl": {
                "subject": "woman",
                "action": "",
                "motion": "soft blink, breath, slow push-in, idle not speaking",
                "camera": {"shot_size": "medium", "angle": "eye level"},
                "cast": ["heroine"],
            },
        }
    ]
    r = lint_dramatic_meaning(
        {
            "heat_scale": "max",
            "dramatic_meaning_strict": True,
            "director_intent": {
                "logline": "test logline long enough",
                "tone": "t",
                "emotional_arc": _good_arc(),
            },
            "scenes": [{"shots": shots}],
        }
    )
    assert not r["ok"]
    assert meaning_gate_enabled({"heat_scale": "max"}) is True


def test_cinematic_audit_surfaces_meaning_codes(tmp_path: Path):
    bad = {
        "scenes": [
            {
                "shots": [
                    {
                        "id": "s1",
                        "dramatic_function": "hook",
                        "duration_sec": 4,
                        "screen_mode": "silence",
                        "dsl": {
                            "motion": "soft blink, breath, slow push-in, hair drift",
                            "camera": {"shot_size": "medium"},
                            "camera_axis": "locked",
                        },
                    }
                ]
            }
        ]
    }
    report = audit(tmp_path, spec=bad)
    assert not report["ok"]
    codes = set(report["blocking_codes"])
    assert (
        CODE_SHOT_MEANING_EMPTY in codes
        or CODE_MOTION_NO_MEANING in codes
        or "BEAT_SEMANTICS_MISS" in codes
        or "PERFORMANCE_DELTA_MISSING" in codes
    )


def test_cinematic_audit_good_meaning_passes(tmp_path: Path):
    arc = _good_arc()
    s1 = _drive_shot("s1", "hook", arc_node=arc[0])
    s1["dsl"]["camera"] = {"shot_size": "wide"}
    s1["dsl"]["camera_axis"] = "pan_with"
    s2 = _drive_shot(
        "s2",
        "approach",
        action="leans closer toward him",
        motion="leans close, reaches for his collar",
        arc_node=arc[1],
    )
    s2["dsl"]["camera"] = {"shot_size": "medium"}
    s2["dsl"]["camera_axis"] = "dolly_in"
    s3 = _drive_shot(
        "s3",
        "reaction",
        action="looks back at the door",
        motion="eyes glance back, soft look",
        visible_change="gaze shifts to the door",
        story_beat="she registers the knock",
        arc_node=arc[2],
    )
    s3["screen_mode"] = "reaction"
    s3["beat_id"] = "b1"
    s3["dsl"]["camera"] = {"shot_size": "close-up"}
    s3["dsl"]["camera_axis"] = "locked"
    s4 = _drive_shot(
        "s4",
        "afterglow",
        action="holds residual heat and softens gaze",
        motion="linger hold, soften blink, residual heat",
        arc_node=arc[3],
    )
    s4["dsl"]["camera"] = {"shot_size": "medium close"}
    s4["dsl"]["camera_axis"] = "pull_back"
    good = {
        "director_intent": {
            "logline": "a deliberate approach across four emotional beats",
            "tone": "intimate",
            "emotional_arc": arc,
        },
        "scenes": [{"shots": [s1, s2, s3, s4]}],
        "transition_intents": ["hard", "hard", "hard"],
    }
    for sh in good["scenes"][0]["shots"]:
        sh.setdefault("screen_mode", "silence")
    report = audit(tmp_path, spec=good)
    assert report["ok"], report["issues"]


def test_preflight_hard_on_meaning_when_max(tmp_path: Path):
    from preflight import run_preflight

    arc = _good_arc()
    bad_spec = {
        "heat_scale": "max",
        "title": "preflight-meaning",
        "director_intent": {
            "logline": "enough chars for logline field",
            "tone": "adult",
            "emotional_arc": arc,
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "s1",
                        "dramatic_function": "hook",
                        "duration_sec": 5,
                        "dsl": {
                            "motion": "soft blink, breath, slow push-in",
                            "arc_node": arc[0],
                            "camera": {"shot_size": "medium"},
                        },
                    },
                    {
                        "id": "s2",
                        "dramatic_function": "action",
                        "duration_sec": 5,
                        "dsl": {
                            "motion": "gentle breath only",
                            "arc_node": arc[0],
                            "camera": {"shot_size": "medium"},
                        },
                    },
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(bad_spec), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    report = run_preflight(tmp_path)
    hard_codes = {i.get("code") for i in report.get("hard") or []}
    assert "dramatic_meaning" in hard_codes or not report.get("ok"), report


def test_api_import_and_return_values():
    empty = lint_shot_meaning([])
    assert empty["ok"] is True
    assert empty["codes"] == []
    motion = lint_motion_purpose(
        [
            {
                "id": "x",
                "dramatic_function": "action",
                "dsl": {"motion": "soft blink, breath, slow push-in"},
            }
        ]
    )
    assert isinstance(motion["codes"], list)
    assert motion["ok"] is False
    stack = lint_emotional_arc_stack([], emotional_arc=["a", "b", "c"])
    assert stack["ok"] is True or CODE_ARC_STACK_NO_MAPPING in stack["codes"] or stack.get(
        "skipped"
    )
