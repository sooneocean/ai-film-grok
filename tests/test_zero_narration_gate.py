"""
Tests for Zero-Narration IRON gate (v2.35.0 · real path 2.36.4)
────────────────────────────────────────────────────────────────
Uses film_spec.zero_narration_gate (no stand-in). dialogue_drama
defaults zero_narration_strict=true → NAR_BUDGET_VIOLATION when nar ratio > 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills" / "ai-film-grok" / "scripts")
)

from film_spec import zero_narration_gate  # noqa: E402


def _make_spec(
    *,
    vo_mode: str = "dialogue_drama",
    zero_narration_strict: bool | None = None,
    shots: list[dict] | None = None,
) -> dict:
    spec: dict = {
        "title": "test-film",
        "vo_mode": vo_mode,
        "scenes": [
            {
                "id": "sc01",
                "shots": shots
                or [
                    {
                        "id": "sh01",
                        "spoken_text": "你终于回来了。",
                        "speaker": "女主",
                        "screen_mode": "on_camera",
                    }
                ],
            }
        ],
    }
    if zero_narration_strict is not None:
        spec["zero_narration_strict"] = zero_narration_strict
    return spec


class TestZeroNarrationDefault:
    def test_pure_dialogue_passes(self) -> None:
        result = zero_narration_gate(_make_spec())
        assert result["ok"] is True
        assert result.get("zero_narration_strict") is True

    def test_third_person_nar_raises_violation(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "nar": "她独自站在雨中，心里一片茫然。",
                }
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"
        assert result["ratio"] == pytest.approx(1.0)

    def test_mixed_dialogue_and_nar_raises_violation(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "spoken_text": "你在等谁？",
                    "speaker": "男主",
                    "screen_mode": "on_camera",
                },
                {
                    "id": "sh02",
                    "nar": "时间仿佛在这一刻停止。",
                },
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"
        assert result["ratio"] == pytest.approx(0.5)

    def test_action_cover_without_nar_passes(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "spoken_text": "我等了很久。",
                    "speaker": "女主",
                    "screen_mode": "on_camera",
                },
                {
                    "id": "sh02",
                    "dramatic_function": "reaction",
                },
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True


class TestZeroNarrationEscape:
    def test_explicit_false_allows_nar(self) -> None:
        spec = _make_spec(
            zero_narration_strict=False,
            shots=[{"id": "sh01", "nar": "某个说书旁白"}],
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True

    def test_non_dialogue_drama_allows_nar(self) -> None:
        spec = _make_spec(
            vo_mode="storyteller",
            shots=[{"id": "sh01", "nar": "她独自站在雨中，心里一片茫然。"}],
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True
        assert result.get("checked") is False

    def test_dialogue_drama_with_explicit_true_still_enforces(self) -> None:
        spec = _make_spec(
            zero_narration_strict=True,
            shots=[{"id": "sh01", "nar": "某个说书旁白"}],
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"


class TestZeroNarrationReplacement:
    def test_prop_insert_sensory_passes(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "spoken_text": "这就是证据。",
                    "speaker": "侦探",
                    "screen_mode": "on_camera",
                },
                {
                    "id": "sh02",
                    "dramatic_function": "sensory",
                    "visible_change": "破碎的怀表特写，表面落满灰尘",
                },
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True

    def test_foley_only_shot_passes(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "spoken_text": "门关上了。",
                    "speaker": "女主",
                    "screen_mode": "off_camera",
                },
                {
                    "id": "sh02",
                    "dramatic_function": "action",
                    "sound_plan": {"events": ["door_slam", "silence_void"]},
                },
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True

    def test_silent_scene_escape_with_reason(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "nar": "雨夜回忆",
                    "silent_scene": True,
                    "narration_reason": "flashback plate no speaker available",
                }
            ]
        )
        result = zero_narration_gate(spec)
        assert result["ok"] is True
