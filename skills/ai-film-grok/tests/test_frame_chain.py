#!/usr/bin/env python3
"""Frame-chain soft lint (lessons-2026-07-20-frame-chain)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from continuity import (  # noqa: E402
    CODE_FRAME_CHAIN_GAP,
    CODE_FRAME_CHAIN_ORPHAN,
    lint_frame_chain,
)


def _shot(
    sid: str,
    beat: str = "action",
    *,
    start: str = "",
    end: str = "",
    mode: str = "",
    action: str = "turns latch",
):
    dsl: dict = {
        "action": action,
        "motion": f"{action}, soft blink, idle not speaking",
        "camera": {"shot_size": "medium", "angle": "eye level"},
    }
    if start:
        dsl["start_pose"] = start
    if end:
        dsl["end_pose"] = end
    if mode:
        dsl["chain_mode"] = mode
    return {"id": sid, "dramatic_function": beat, "dsl": dsl}


def test_soft_join_missing_poses_flags_gap():
    shots = [
        _shot("shot01", end=""),
        _shot("shot02", start=""),
    ]
    r = lint_frame_chain(shots, transition_intents=["soft"])
    assert CODE_FRAME_CHAIN_GAP in r["codes"]
    assert r["warning_count"] >= 1


def test_soft_join_with_poses_ok():
    shots = [
        _shot("shot01", start="at door", end="latch shut hand down"),
        _shot("shot02", start="latch shut hand down", end="steps to vanity", mode="continue"),
    ]
    r = lint_frame_chain(shots, transition_intents=["soft"])
    assert CODE_FRAME_CHAIN_GAP not in r["codes"]
    assert r["ok"] is True


def test_hard_join_skips_pose_requirement():
    shots = [
        _shot("shot01"),  # no poses
        _shot("shot02"),
    ]
    r = lint_frame_chain(shots, transition_intents=["hard"])
    assert CODE_FRAME_CHAIN_GAP not in r["codes"]


def test_cut_mode_on_soft_is_orphan():
    shots = [
        _shot("shot01", start="a", end="b", mode="continue"),
        _shot("shot02", start="b", end="c", mode="cut"),
    ]
    r = lint_frame_chain(shots, transition_intents=["soft"])
    assert CODE_FRAME_CHAIN_ORPHAN in r["codes"]


def test_hold_join_also_requires_chain():
    shots = [
        _shot("s1", beat="action"),
        _shot("s2", beat="afterglow"),
    ]
    r = lint_frame_chain(shots, transition_intents=["hold"])
    assert CODE_FRAME_CHAIN_GAP in r["codes"]
