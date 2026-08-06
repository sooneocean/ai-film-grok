from __future__ import annotations

import copy
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_bible import validate_audio_bible  # noqa: E402


def _bible() -> dict:
    return {
        "state": "locked",
        "nodes": {
            "voice": {
                "state": "locked",
                "data": {
                    "characters": {
                        "hero": {
                            "provider": "edge",
                            "voice_id": "zh-CN-XiaoxiaoNeural",
                            "rate": "+0%",
                            "emphasis": "moderate",
                            "pauses_ms": [120, 240],
                            "emotion_range": ["intimate", "urgent"],
                        }
                    }
                },
            },
            "dialogue_delivery": {
                "state": "locked",
                "data": {
                    "key_dialogue": [
                        {
                            "line_id": "line-1",
                            "character_id": "hero",
                            "text_sha256": "a" * 64,
                            "delivery": "breath held, then firm",
                            "lipsync_required": True,
                        }
                    ]
                },
            },
            "bgm_motif_cue": {
                "state": "locked",
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
                },
            },
        },
    }


def test_locked_audio_bible_requires_complete_voice_and_key_dialogue_contract() -> None:
    report = validate_audio_bible(_bible())

    assert report["ok"], report


def test_provider_change_cannot_be_silent() -> None:
    previous = _bible()
    current = copy.deepcopy(previous)
    current["nodes"]["voice"]["data"]["characters"]["hero"]["provider"] = "azure"

    stale = validate_audio_bible(current, previous=previous)
    assert "VOICE_PROVIDER_CHANGED_UNACKNOWLEDGED" in {issue["code"] for issue in stale["errors"]}

    current["provider_change"] = {
        "from": "edge",
        "to": "azure",
        "reason": "licensed performance retake",
        "approved_by": "human",
    }
    assert validate_audio_bible(current, previous=previous)["ok"]


def test_locked_voice_rejects_missing_performance_controls() -> None:
    bible = _bible()
    del bible["nodes"]["voice"]["data"]["characters"]["hero"]["emotion_range"]

    report = validate_audio_bible(bible)

    assert "VOICE_LOCK_INCOMPLETE" in {issue["code"] for issue in report["errors"]}


def test_bgm_requires_motif_cues_silence_license_and_ducking() -> None:
    bible = _bible()
    del bible["nodes"]["bgm_motif_cue"]["data"]["cues"][0]["ducking_db"]

    report = validate_audio_bible(bible)

    assert "BGM_CUE_INVALID" in {issue["code"] for issue in report["errors"]}
