from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, _validate_dialogue_drama_shot  # noqa: E402


def _narration_shot() -> dict:
    return {
        "id": "gap01",
        "screen_mode": "action_cover",
        "narration_reason": "time jump",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "narration",
                "spoken_text": "三天后，她回到车站。",
                "start_offset_sec": 0,
                "duration_sec": 2,
            }
        ],
        "must_show": "她推开车站的门",
        "visible_change": "门从关闭到打开",
        "dsl": {"action": "she opens the station door"},
    }


def test_strict_gap_narration_requires_reasoned_uncovered_information() -> None:
    shot = _narration_shot()
    with pytest.raises(FilmSpecError, match="narration_gap evidence"):
        _validate_dialogue_drama_shot(
            shot,
            shot_id="gap01",
            narration_gap_strict=True,
        )

    shot["narration_gap"] = {
        "reason": "time_jump",
        "uncovered_information": "three days elapsed off screen",
        "source_refs": ["source:paragraph-4"],
    }
    _validate_dialogue_drama_shot(
        shot,
        shot_id="gap01",
        narration_gap_strict=True,
    )


def test_strict_gap_narration_rejects_visual_duplication() -> None:
    shot = _narration_shot()
    shot["audio_cues"][0]["spoken_text"] = "门从关闭到打开"
    shot["narration_gap"] = {
        "reason": "offscreen_fact",
        "uncovered_information": "door movement",
    }
    with pytest.raises(FilmSpecError, match="duplicates visible information"):
        _validate_dialogue_drama_shot(
            shot,
            shot_id="gap01",
            narration_gap_strict=True,
        )
