#!/usr/bin/env python3
"""Long-form continuity_chain.md + byte-identical join gates."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from continuity_chain import (  # noqa: E402
    CODE_BYTE_MISMATCH,
    CODE_COVERUP_DISSOLVE,
    CODE_COVERUP_MOTION,
    CODE_MISSING_CHAIN_DOC,
    check_continuity_chain,
    init_chain_doc,
    is_long_form,
    upsert_join,
)


def _spec(n: int = 6) -> dict:
    shots = []
    for i in range(1, n + 1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "dramatic_function": "action" if i < n else "afterglow",
                "nar": "测",
                "duration_sec": 6,
                "dsl": {
                    "action": "steps",
                    "motion": "steps forward, idle not speaking",
                    "start_pose": "a",
                    "end_pose": "b",
                    "chain_mode": "continue",
                },
            }
        )
    return {
        "title": "test-chain",
        "director_intent": {
            "logline": "测试长片动作链",
            "tone": "test",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": [{"shots": shots}],
    }


def test_is_long_form_by_shot_count():
    assert is_long_form(_spec(6)) is True
    assert is_long_form(_spec(3)) is False


def test_is_long_form_flag():
    s = _spec(2)
    s["long_form"] = True
    assert is_long_form(s) is True


def test_missing_doc_hard_for_long():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        report = check_continuity_chain(root, _spec(6), require_doc_if_long=True)
        assert CODE_MISSING_CHAIN_DOC in report["codes"]
        assert report["ok"] is False


def test_init_creates_doc():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = init_chain_doc(root, _spec(6))
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "Join: shot01 → shot02" in text
        assert "姿势 pose" in text
        report = check_continuity_chain(root, _spec(6))
        assert CODE_MISSING_CHAIN_DOC not in report["codes"]


def test_byte_mismatch_hard():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        init_chain_doc(root, _spec(6))
        upsert_join(
            root,
            from_id="shot01",
            to_id="shot02",
            mode="continue",
            last_sha="aaa",
            first_sha="bbb",
        )
        report = check_continuity_chain(root, _spec(6))
        assert CODE_BYTE_MISMATCH in report["codes"]
        assert report["ok"] is False


def test_byte_identical_ok():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        init_chain_doc(root, _spec(6))
        upsert_join(
            root,
            from_id="shot01",
            to_id="shot02",
            mode="continue",
            last_sha="same",
            first_sha="same",
        )
        report = check_continuity_chain(root, _spec(6))
        assert CODE_BYTE_MISMATCH not in report["codes"]
        assert report["ok"] is True


def _root_with_identical_join(n: int = 6) -> tuple:
    """Return (root, spec) with continuity_chain.md + one byte-identical continue join."""
    import tempfile

    root = Path(tempfile.mkdtemp())
    spec = _spec(n)
    init_chain_doc(root, spec)
    upsert_join(
        root,
        from_id=f"shot{n - 1:02d}",
        to_id=f"shot{n:02d}",
        mode="continue",
        last_sha="same",
        first_sha="same",
        checklist={k: "pass" for k in (
            "pose", "gaze", "hands_props", "travel", "axis",
            "hair", "wardrobe", "weather", "lighting",
        )},
    )
    return root, spec


def test_coverup_dissolve_soft_by_default():
    root, spec = _root_with_identical_join()
    spec["transition_sec"] = 0.3
    spec["transition_default"] = "soft"
    report = check_continuity_chain(root, spec, strict=False)
    assert CODE_COVERUP_DISSOLVE in report["codes"]
    iss = next(i for i in report["issues"] if i["code"] == CODE_COVERUP_DISSOLVE)
    assert iss["severity"] == "warning"
    # soft advisory must not fail the report by itself
    assert report["ok"] is True


def test_coverup_dissolve_hard_under_strict():
    root, spec = _root_with_identical_join()
    spec["transition_sec"] = 0.3
    spec["transition_default"] = "soft"
    report = check_continuity_chain(root, spec, strict=True)
    iss = next(i for i in report["issues"] if i["code"] == CODE_COVERUP_DISSOLVE)
    assert iss["severity"] == "error"
    assert report["ok"] is False


def test_no_coverup_on_hard_match_cut():
    root, spec = _root_with_identical_join()
    spec["transition_sec"] = 0.3
    spec["transition_default"] = "hard"
    report = check_continuity_chain(root, spec, strict=True)
    assert CODE_COVERUP_DISSOLVE not in report["codes"]
    assert report["ok"] is True


def test_coverup_motion_freeze_advisory():
    root, spec = _root_with_identical_join()
    # inject a forbidden motion token on the continue join's `to` shot
    last = spec["scenes"][0]["shots"][-1]
    last["dsl"] = dict(last.get("dsl", {}))
    last["dsl"]["motion"] = "定格 hold end_pose to mask jump"
    report = check_continuity_chain(root, spec, strict=True)
    assert CODE_COVERUP_MOTION in report["codes"]
    iss = next(i for i in report["issues"] if i["code"] == CODE_COVERUP_MOTION)
    assert iss["severity"] == "warning"
