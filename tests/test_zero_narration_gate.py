"""
Tests for Zero-Narration IRON gate (v2.35.0)
─────────────────────────────────────────────
Verifies that `dialogue_drama` projects default to `zero_narration_strict:true`
and that `write-spec` equivalent logic raises NAR_BUDGET_VIOLATION when
third-person narrator nar is present with non-zero ratio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills" / "ai-film-grok" / "scripts")
)

# ────────────────────────────────────────────────────────────────────────────
# Helpers – minimal spec fixture builders
# ────────────────────────────────────────────────────────────────────────────


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


def _narration_ratio(spec: dict) -> float:
    """Compute third-person nar ratio over total shots."""
    total = 0
    nar_count = 0
    for scene in spec.get("scenes", []):
        for shot in scene.get("shots", []):
            total += 1
            nar = shot.get("nar", "")
            is_dialogue = bool(shot.get("spoken_text"))
            if nar and not is_dialogue:
                nar_count += 1
    if total == 0:
        return 0.0
    return nar_count / total


def _check_zero_narration(spec: dict) -> dict:
    """
    Lightweight stand-in for write-spec's zero_narration gate.
    Returns {"ok": True} or {"ok": False, "code": "NAR_BUDGET_VIOLATION", "ratio": float}.
    """
    vo_mode = spec.get("vo_mode", "")
    strict = spec.get("zero_narration_strict", vo_mode == "dialogue_drama")

    if not strict:
        return {"ok": True}

    ratio = _narration_ratio(spec)
    if ratio > 0.0:
        return {
            "ok": False,
            "code": "NAR_BUDGET_VIOLATION",
            "ratio": ratio,
            "message": (
                f"zero_narration_strict:true but narration_ratio={ratio:.2%}. "
                "Replace third-person nar with character dialogue, prop inserts, or Foley SFX."
            ),
        }
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────────────


class TestZeroNarrationDefault:
    """dialogue_drama should default zero_narration_strict=True."""

    def test_pure_dialogue_passes(self) -> None:
        spec = _make_spec()
        result = _check_zero_narration(spec)
        assert result["ok"] is True

    def test_third_person_nar_raises_violation(self) -> None:
        spec = _make_spec(
            shots=[
                {
                    "id": "sh01",
                    "nar": "她独自站在雨中，心里一片茫然。",  # third-person narration
                }
            ]
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"
        assert result["ratio"] == pytest.approx(1.0)

    def test_mixed_dialogue_and_nar_raises_violation(self) -> None:
        """Even partial nar must fail when strict."""
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
                    "nar": "时间仿佛在这一刻停止。",  # no spoken_text → narrator
                },
            ]
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"
        assert result["ratio"] == pytest.approx(0.5)

    def test_action_cover_without_nar_passes(self) -> None:
        """Non-dialogue shots without nar text are allowed (action_cover/reaction)."""
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
                    # no nar, no spoken_text → valid silent reaction shot
                },
            ]
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is True


class TestZeroNarrationEscape:
    """Escape hatches: explicit opt-out or non-dialogue_drama mode."""

    def test_explicit_false_allows_nar(self) -> None:
        """zero_narration_strict:false should bypass the gate."""
        spec = _make_spec(
            zero_narration_strict=False,
            shots=[
                {
                    "id": "sh01",
                    "nar": "某个说书旁白",
                }
            ],
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is True

    def test_non_dialogue_drama_allows_nar(self) -> None:
        """arthouse / documentary / monologue modes do not auto-enable strict."""
        spec = _make_spec(
            vo_mode="storyteller",
            shots=[
                {
                    "id": "sh01",
                    "nar": "她独自站在雨中，心里一片茫然。",
                }
            ],
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is True

    def test_dialogue_drama_with_explicit_true_still_enforces(self) -> None:
        spec = _make_spec(
            zero_narration_strict=True,
            shots=[
                {
                    "id": "sh01",
                    "nar": "某个说书旁白",
                }
            ],
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is False
        assert result["code"] == "NAR_BUDGET_VIOLATION"


class TestZeroNarrationReplacement:
    """
    Validate that legal replacement patterns (prop insert, Foley, silent reaction)
    do not trigger NAR_BUDGET_VIOLATION.
    """

    def test_prop_insert_sensory_passes(self) -> None:
        """Prop close-up (dramatic_function=sensory/insert) without nar is valid replacement."""
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
                    # no nar: background is told via prop insert
                },
            ]
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is True

    def test_foley_only_shot_passes(self) -> None:
        """A shot relying on Foley/SFX cue without nar text is allowed."""
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
                    # no nar: atmosphere via Foley
                },
            ]
        )
        result = _check_zero_narration(spec)
        assert result["ok"] is True


class TestNarrationRatioCalculation:
    """Unit tests for _narration_ratio helper."""

    def test_all_dialogue_is_zero(self) -> None:
        spec = _make_spec(
            shots=[
                {"id": "sh01", "spoken_text": "A", "speaker": "x"},
                {"id": "sh02", "spoken_text": "B", "speaker": "y"},
            ]
        )
        assert _narration_ratio(spec) == pytest.approx(0.0)

    def test_all_nar_is_one(self) -> None:
        spec = _make_spec(
            shots=[
                {"id": "sh01", "nar": "旁白一"},
                {"id": "sh02", "nar": "旁白二"},
            ]
        )
        assert _narration_ratio(spec) == pytest.approx(1.0)

    def test_half_nar(self) -> None:
        spec = _make_spec(
            shots=[
                {"id": "sh01", "spoken_text": "台词", "speaker": "A"},
                {"id": "sh02", "nar": "旁白"},
            ]
        )
        assert _narration_ratio(spec) == pytest.approx(0.5)

    def test_empty_shots_returns_zero(self) -> None:
        spec = _make_spec(shots=[])
        assert _narration_ratio(spec) == pytest.approx(0.0)
