"""Director content channels: text never silently becomes performance."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from content_channels import (  # noqa: E402
    lint_content_channels,
    resolve_content_channels,
    visual_prompt_action,
)
from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from prompt_injector import PromptInjector  # noqa: E402


def test_narration_never_becomes_motion_prompt(tmp_path: Path) -> None:
    shot = {"id": "s1", "nar": "她说：别回头。", "lipsync": False, "dsl": {}}
    assert visual_prompt_action(shot) == ""
    receipt = PromptInjector({}, template_version="I2V").assemble(shot, tmp_path)
    assert "她说：别回头" not in receipt["prompt_text"]
    assert "Narration is audio-only" in receipt["prompt_text"]


def test_visible_reaction_is_bound_to_scene_event() -> None:
    shot = {
        "id": "s2",
        "nar": "门后有人。",
        "dsl": {"action": "she freezes and turns toward the door"},
        "content_channels": {
            "voice": {"kind": "narration", "on_camera": False},
            "performance": {
                "playable_action": "her hand stops mid-air",
                "reaction_trigger": "the door handle turns",
            },
            "motion": {"scene_trigger": "the door handle turns"},
        },
    }
    channels = resolve_content_channels(shot)
    assert channels["motion"]["scene_trigger"] == "the door handle turns"
    assert lint_content_channels([shot])["ok"]


def test_on_camera_dialogue_requires_lipsync() -> None:
    report = lint_content_channels(
        [
            {
                "id": "s3",
                "dialogue": "你来了。",
                "speaker_on_camera": True,
                "lipsync": False,
                "content_channels": {"voice": {"kind": "dialogue", "on_camera": True}},
            }
        ]
    )
    assert "ON_CAMERA_DIALOGUE_LIPSYNC_OFF" in report["codes"]


def test_strict_spec_rejects_text_as_action() -> None:
    spec = {
        "title": "频道契约",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "dramatic_meaning_strict": False,
        "director_intent": {
            "logline": "这是一个足够长的频道契约测试。",
            "tone": "test",
            "emotional_arc": ["a", "b", "c"],
        },
        "content_channels_strict": True,
        "scenes": [
            {
                "title": "s",
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "门开了。",
                        "duration_sec": 4,
                        "dsl": {"action": "门开了。", "motion": "push_in"},
                    }
                ],
            }
        ],
    }
    with pytest.raises(FilmSpecError, match="TEXT_USED_AS_VISUAL_ACTION"):
        validate_film_spec(spec, assign_missing_ids=False)
