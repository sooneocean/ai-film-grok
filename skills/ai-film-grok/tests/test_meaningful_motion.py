#!/usr/bin/env python3
"""Meaningful motion lint (lessons-2026-07-20-meaningful-motion)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from continuity import (  # noqa: E402
    CODE_BEAT_SEMANTICS_MISS,
    CODE_MOTION_NO_MEANING,
    lint_meaningful_motion,
)


def _shot(sid: str, beat: str, *, action: str = "", motion: str = "", **extra):
    dsl = {"action": action, "motion": motion, "camera": {"shot_size": "medium"}}
    dsl.update(extra)
    return {"id": sid, "dramatic_function": beat, "dsl": dsl}


def test_aesthetic_only_hook_flags_no_meaning():
    shots = [
        _shot(
            "s1",
            "hook",
            action="",
            motion="soft blink, breath, slow push-in, hair drift, idle not speaking",
        )
    ]
    r = lint_meaningful_motion(shots)
    assert CODE_MOTION_NO_MEANING in r["codes"] or CODE_BEAT_SEMANTICS_MISS in r["codes"]


def test_hook_with_enter_semantics_ok():
    shots = [
        _shot(
            "s1",
            "hook",
            action="pulls curtain and steps into light",
            motion="hand pulls curtain aside, steps forward into vanity light, idle not speaking",
            visible_change="from corridor dark into lit dressing room",
            story_beat="she claims the room entrance",
        )
    ]
    r = lint_meaningful_motion(shots)
    assert CODE_MOTION_NO_MEANING not in r["codes"]
    assert CODE_BEAT_SEMANTICS_MISS not in r["codes"]


def test_action_beat_missing_semantics():
    shots = [
        _shot(
            "s1",
            "action",
            action="soft look",
            motion="soft blink, gentle breath, camera slow push-in",
        )
    ]
    r = lint_meaningful_motion(shots)
    assert CODE_BEAT_SEMANTICS_MISS in r["codes"] or CODE_MOTION_NO_MEANING in r["codes"]


def test_sensory_breath_ok():
    shots = [
        _shot(
            "s1",
            "sensory",
            action="chest rises with breath, sweat bead on collarbone",
            motion="slow breath rise, sweat bead slides on collarbone, idle not speaking",
        )
    ]
    r = lint_meaningful_motion(shots)
    assert CODE_BEAT_SEMANTICS_MISS not in r["codes"]
