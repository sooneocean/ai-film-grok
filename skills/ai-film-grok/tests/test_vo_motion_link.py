#!/usr/bin/env python3
"""VO–motion link / anti-fatigue soft lint (lessons-2026-07-17-vo-motion-link)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from continuity import (  # noqa: E402
    CODE_MOTION_MONOTONY,
    CODE_PRIMARY_MOTION_WEAK,
    CODE_SIZE_FLAT,
    CODE_SOFT_SOUP,
    lint_vo_motion_link,
)


def _shot(
    sid: str,
    beat: str,
    *,
    motion: str,
    action: str = "",
    size: str = "close-up",
    angle: str = "eye level",
):
    return {
        "id": sid,
        "dramatic_function": beat,
        "dsl": {
            "action": action,
            "motion": motion,
            "camera": {"shot_size": size, "angle": angle},
        },
    }


def test_primary_motion_weak_on_action_blink_only():
    shots = [
        _shot(
            "shot01",
            "action",
            motion="soft blink, breath, slow push-in, hair drift, idle not speaking",
        ),
    ]
    r = lint_vo_motion_link(shots)
    assert CODE_PRIMARY_MOTION_WEAK in r["codes"]
    assert r["warning_count"] >= 1


def test_primary_ok_when_action_verb_leads():
    shots = [
        _shot(
            "shot01",
            "action",
            action="unhooks gold buckle, coat slips off shoulder",
            motion="unhook buckle, coat slide, then soft blink, idle not speaking",
            size="medium full",
        ),
    ]
    r = lint_vo_motion_link(shots)
    assert CODE_PRIMARY_MOTION_WEAK not in r["codes"]


def test_monotony_three_micro_shots():
    shots = [
        _shot("s1", "sensory", motion="soft blink, breath, slow push-in"),
        _shot("s2", "reaction", motion="soft blink, breath, slow push-in"),
        _shot("s3", "afterglow", motion="soft blink, breath, slow push-in"),
    ]
    r = lint_vo_motion_link(shots)
    assert CODE_MOTION_MONOTONY in r["codes"]


def test_size_flat_three_closeups():
    shots = [
        _shot(
            "s1",
            "action",
            action="turns latch",
            motion="hand turns latch shut, soft blink",
            size="close-up",
        ),
        _shot(
            "s2",
            "action",
            action="unhooks buckle",
            motion="unhook buckle, coat slip, soft blink",
            size="close-up",
        ),
        _shot(
            "s3",
            "action",
            action="pulls belt",
            motion="belt pull, hip shift, soft blink",
            size="close-up",
        ),
    ]
    r = lint_vo_motion_link(shots)
    assert CODE_SIZE_FLAT in r["codes"]


def test_soft_soup():
    shots = [
        _shot(f"s{i}", "bridge", motion="gentle continuous pan, soft blink", size="medium")
        for i in range(6)
    ]
    # give them primary-ish tokens so monotony is not the only code
    for s in shots:
        s["dsl"]["action"] = "walks past lamp"
        s["dsl"]["motion"] = "walk past lamp, gentle pan, soft blink"
    r = lint_vo_motion_link(shots, transition_intents=["soft"] * 5)
    assert CODE_SOFT_SOUP in r["codes"]


def test_varied_window_clean():
    shots = [
        _shot(
            "s1",
            "hook",
            action="hand on door latch",
            motion="hand turns latch shut, then soft blink",
            size="medium full",
            angle="eye level",
        ),
        _shot(
            "s2",
            "sensory",
            action="breath on collarbone",
            motion="chest breathing rise, continuous slow push-in",
            size="extreme close-up",
            angle="eye level",
        ),
        _shot(
            "s3",
            "action",
            action="leans over viewer",
            motion="lean-in body move, hair fall, soft blink",
            size="close-up",
            angle="slight low",
        ),
    ]
    r = lint_vo_motion_link(shots, transition_intents=["soft", "hard"])
    assert CODE_PRIMARY_MOTION_WEAK not in r["codes"]
    assert CODE_MOTION_MONOTONY not in r["codes"]
    assert CODE_SIZE_FLAT not in r["codes"]
    assert CODE_SOFT_SOUP not in r["codes"]


if __name__ == "__main__":
    test_primary_motion_weak_on_action_blink_only()
    test_primary_ok_when_action_verb_leads()
    test_monotony_three_micro_shots()
    test_size_flat_three_closeups()
    test_soft_soup()
    test_varied_window_clean()
    print("ok")
