from __future__ import annotations

import copy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_bible import validate_post_bible  # noqa: E402


def _post() -> dict:
    return {
        "state": "locked",
        "nodes": {
            "captions": {
                "data": {
                    "render_owner": "ffmpeg",
                    "active_renderers": ["ffmpeg"],
                    "cues": [
                        {
                            "cue_id": "cue-1",
                            "shot_window": {"start_sec": 0.0, "end_sec": 2.0},
                            "dialogue_window": {"start_sec": 0.2, "end_sec": 1.4},
                            "start_sec": 0.2,
                            "end_sec": 1.4,
                        }
                    ],
                    "srt_sha256": "1" * 64,
                }
            },
            "mix": {
                "data": {
                    "stems": [
                        {"kind": kind, "sha256": str(index) * 64}
                        for index, kind in enumerate(
                            ["dialogue", "vo", "native", "ambience", "foley", "sfx", "bgm"],
                            start=2,
                        )
                    ],
                    "integrated_lufs": -16.0,
                    "true_peak_dbtp": -1.0,
                    "degraded_from": None,
                    "mix_sha256": "9" * 64,
                }
            },
            "bgm_motif_cue": {
                "data": {
                    "motif": "restless pulse",
                    "cues": [
                        {
                            "cue_id": "music-1",
                            "in_sec": 0.0,
                            "out_sec": 1.8,
                            "silence_before_sec": 0.2,
                            "silence_after_sec": 0.2,
                            "ducking_db": -8.0,
                        }
                    ],
                    "license": {"source": "library", "license_id": "lic-1"},
                }
            },
            "master": {
                "data": {
                    "final_sha256": "a" * 64,
                    "mix_sha256": "9" * 64,
                    "srt_sha256": "1" * 64,
                    "approval": {
                        "approver_type": "human",
                        "input_hashes": {
                            "final": "a" * 64,
                            "mix": "9" * 64,
                            "srt": "1" * 64,
                        },
                    },
                    "automated_score": {"score": 0.99, "decision": "advisory"},
                }
            },
        },
    }


def test_complete_post_bible_closes_music_mix_caption_and_master_contracts() -> None:
    assert validate_post_bible(_post())["ok"]


def test_captions_require_one_owner_and_stay_inside_both_windows() -> None:
    post = _post()
    captions = post["nodes"]["captions"]["data"]
    captions["active_renderers"].append("hyperframes")
    captions["cues"][0]["end_sec"] = 1.6

    report = validate_post_bible(post)

    codes = {issue["code"] for issue in report["errors"]}
    assert "CAPTION_RENDER_OWNER_CONFLICT" in codes
    assert "CAPTION_OUTSIDE_DIALOGUE_WINDOW" in codes


def test_mix_srt_or_final_change_invalidates_master_approval() -> None:
    post = _post()
    post["nodes"]["master"]["data"]["mix_sha256"] = "e" * 64

    report = validate_post_bible(post)

    assert "MASTER_APPROVAL_STALE" in {issue["code"] for issue in report["errors"]}


def test_automated_score_cannot_claim_human_pass() -> None:
    post = copy.deepcopy(_post())
    post["nodes"]["master"]["data"]["approval"]["approver_type"] = "automated"
    post["nodes"]["master"]["data"]["automated_score"]["decision"] = "pass"

    report = validate_post_bible(post)

    codes = {issue["code"] for issue in report["errors"]}
    assert "MASTER_HUMAN_APPROVAL_REQUIRED" in codes
    assert "AUTOMATED_SCORE_MUST_BE_ADVISORY" in codes
