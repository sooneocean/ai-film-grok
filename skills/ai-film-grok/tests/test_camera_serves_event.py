"""Wave β: camera serves visible_change; no empty push-in; adjacent framing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity import (  # noqa: E402
    CODE_CAMERA_WITHOUT_EVENT,
    CODE_MOTION_NO_MEANING,
    lint_meaningful_motion,
)
from motion_prompt_spine import (  # noqa: E402
    MotionCoreError,
    assert_motion_prompt_core,
    build_motion_prompt,
)
from workflow_pack import variety_precheck  # noqa: E402


def test_build_motion_prompt_no_silent_push_in_pad() -> None:
    body = build_motion_prompt({}, {"id": "s1"}, mode="i2v", include_provider_prefix=False)
    assert "subtle camera push-in" not in body.lower()


def test_assert_rejects_camera_only_hero_prompt() -> None:
    shot = {
        "id": "s_drive",
        "shot_role": "hero",
        "dramatic_function": "action",
        "dsl": {},
    }
    with pytest.raises(MotionCoreError) as ei:
        assert_motion_prompt_core(
            "Vertical 9:16. subtle camera push-in, soft blink, natural motion.",
            shot,
            mode="i2v",
            role="hero",
        )
    assert "CAMERA_ONLY" in str(ei.value) or "NO_ACTION" in str(ei.value)


def test_assert_accepts_body_action() -> None:
    shot = {
        "id": "s_ok",
        "shot_role": "hero",
        "dramatic_function": "action",
        "dsl": {
            "action": "turns the latch shut with fingertips",
            "visible_change": "door latch from open to closed",
            "motion": "reaches latch, turns it shut, body angles to vanity",
        },
    }
    rep = assert_motion_prompt_core(
        "Dramatic function: action. She turns the door latch shut. "
        "Hand reaches metal bolt. Camera holds medium close.",
        shot,
        mode="i2v",
        role="hero",
    )
    assert rep["ok"] is True


def test_lint_camera_without_event() -> None:
    shots = [
        {
            "id": "s01",
            "dramatic_function": "action",
            "dsl": {
                "motion": "slow continuous push-in, soft blink, breath",
                "camera_prompt": "slow push-in",
                "camera_axis": "push-in",
            },
        }
    ]
    rep = lint_meaningful_motion(shots)
    codes = set(rep.get("codes") or [])
    assert CODE_CAMERA_WITHOUT_EVENT in codes or CODE_MOTION_NO_MEANING in codes
    assert rep.get("ok") is False or rep.get("error_count", 0) > 0


def test_variety_adjacent_framing_collision(tmp_path: Path) -> None:
    spec = {
        "title": "v",
        "heat_scale": "max",
        "scenes": [
            {
                "shots": [
                    {
                        "id": "a1",
                        "heat_phase": "act",
                        "sex_pose": "cowgirl",
                        "shot_size": "ms",
                        "duration_sec": 6,
                        "dsl": {
                            "motion": "thrust A slow",
                            "camera_axis": "push-in",
                            "camera": {"shot_size": "ms", "move": "push-in"},
                            "action": "hip thrust continuous",
                        },
                    },
                    {
                        "id": "a2",
                        "heat_phase": "act",
                        "sex_pose": "missionary",
                        "shot_size": "ms",
                        "duration_sec": 6,
                        "dsl": {
                            "motion": "thrust B hard",
                            "camera_axis": "push-in",
                            "camera": {"shot_size": "ms", "move": "push-in"},
                            "action": "hip thrust harder",
                        },
                    },
                    {
                        "id": "a3",
                        "heat_phase": "climax",
                        "sex_pose": "from_behind",
                        "shot_size": "cu",
                        "duration_sec": 6,
                        "dsl": {
                            "motion": "peak shake",
                            "camera_axis": "orbit",
                            "camera": {"shot_size": "cu", "move": "orbit"},
                            "action": "climax hold",
                        },
                    },
                    {
                        "id": "a4",
                        "heat_phase": "climax",
                        "sex_pose": "side",
                        "shot_size": "insert",
                        "duration_sec": 6,
                        "dsl": {
                            "motion": "detail grip",
                            "camera_axis": "handheld",
                            "camera": {"shot_size": "insert", "move": "handheld"},
                            "action": "hand grip",
                        },
                    },
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rep = variety_precheck(tmp_path, write=False)
    codes = {i.get("code") for i in rep.get("issues") or []}
    assert "ADJACENT_FRAMING_COLLISION" in codes or "ADJACENT_CAMERA_COLLISION" in codes
