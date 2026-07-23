from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_contract import validate_dialogue_contract  # noqa: E402


def _contract() -> dict:
    return {
        "shot_id": "shot01",
        "shot_window": {"start_sec": 10.0, "end_sec": 12.0},
        "lines": [
            {
                "line_id": "line-1",
                "text_sha256": "b" * 64,
                "delivery": "quiet warning",
                "window": {"start_sec": 10.2, "end_sec": 11.4},
                "audio_origin": "native",
                "lipsync_required": True,
                "lipsync_evidence": {
                    "method": "generated_native_audio",
                    "artifact_sha256": "c" * 64,
                },
            }
        ],
    }


def test_native_dialogue_with_true_lipsync_evidence_is_valid() -> None:
    assert validate_dialogue_contract(_contract())["ok"]


def test_silent_i2v_with_post_vo_is_not_native_audio_or_true_lipsync() -> None:
    contract = _contract()
    line = contract["lines"][0]
    line["audio_origin"] = "post_vo"
    line["source_video_audio"] = "silent"
    line["lipsync_evidence"] = {
        "method": "timed_post_vo",
        "artifact_sha256": "d" * 64,
    }

    report = validate_dialogue_contract(contract)

    codes = {issue["code"] for issue in report["errors"]}
    assert "POST_VO_NOT_NATIVE_AUDIO" in codes
    assert "TRUE_LIPSYNC_EVIDENCE_MISSING" in codes


def test_dialogue_must_remain_inside_shot_window() -> None:
    contract = _contract()
    contract["lines"][0]["window"]["end_sec"] = 12.1

    report = validate_dialogue_contract(contract)

    assert "DIALOGUE_OUTSIDE_SHOT_WINDOW" in {issue["code"] for issue in report["errors"]}
