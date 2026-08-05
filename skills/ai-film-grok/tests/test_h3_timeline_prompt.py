"""H3 Layer-4 timeline prompt compiler unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_timeline_prompt import (  # noqa: E402
    build_reference_composition_prompt,
    format_timecode,
    inject_2v_reference_stage,
    plan_segment_bounds,
    resolve_duration_sec,
    segment_count_for,
    supports_image_input,
    validate_timeline_coverage,
)


def test_plan_segment_bounds_no_gaps() -> None:
    bounds = plan_segment_bounds(8, 3)
    assert bounds[0][0] == 0.0
    assert bounds[-1][1] == 8.0
    for i in range(len(bounds) - 1):
        assert bounds[i][1] == bounds[i + 1][0]


def test_segment_count_density_guide() -> None:
    assert 2 <= segment_count_for(5, prompt_tier="medium") <= 3
    assert 3 <= segment_count_for(8, prompt_tier="medium") <= 4
    assert segment_count_for(5, prompt_tier="soft") <= segment_count_for(
        5, prompt_tier="high"
    )


def test_resolve_duration_from_shot() -> None:
    assert resolve_duration_sec({"duration_sec": 6}) == 6.0
    assert resolve_duration_sec({"dsl": {"duration_sec": 4}}) == 4.0


def test_validate_timeline_ok() -> None:
    text = "\n".join(
        [
            f"{format_timecode(0, 3)} walk begins.",
            f"{format_timecode(3, 6)} walk continues.",
            f"{format_timecode(6, 8)} holds end pose.",
        ]
    )
    r = validate_timeline_coverage(text, duration_sec=8)
    assert r["ok"] is True
    assert r["segment_count"] == 3


def test_validate_timeline_gap_detected() -> None:
    text = "[0s-2s] a.\n[4s-6s] b."
    r = validate_timeline_coverage(text)
    assert r["ok"] is False
    assert r["error"] and "GAP" in r["error"]


# ── 2V Reference Stage tests ──────────────────────────


def test_supports_image_input_i2v() -> None:
    assert supports_image_input("i2v") is True


def test_supports_image_input_flf() -> None:
    assert supports_image_input("flf") is True


def test_supports_image_input_r2v() -> None:
    assert supports_image_input("r2v") is True


def test_supports_image_input_t2v() -> None:
    assert supports_image_input("t2v") is False


def test_supports_image_input_case_insensitive() -> None:
    assert supports_image_input("I2V") is True
    assert supports_image_input("  i2v  ") is True


def test_build_reference_composition_prompt_basic() -> None:
    shot = {
        "dramatic_function": "action",
        "dsl": {
            "environment": "neon-lit rain-soaked street",
            "subject": "a young woman in a beige trench coat",
            "camera": {"shot_size": "cu"},
            "lighting": "neon reflections on wet pavement",
        },
    }
    prompt = build_reference_composition_prompt(shot)
    assert "neon-lit rain-soaked street" in prompt
    assert "a young woman in a beige trench coat" in prompt
    assert "9:16 aspect ratio" in prompt
    assert "start frame" in prompt


def test_build_reference_composition_prompt_fallbacks() -> None:
    shot = {}
    prompt = build_reference_composition_prompt(shot)
    assert "a cinematic scene" in prompt
    assert "the main character" in prompt
    assert "natural cinematic lighting" in prompt


def test_build_reference_composition_prompt_with_mood() -> None:
    shot = {"dsl": {"environment": "a quiet room"}}
    prompt = build_reference_composition_prompt(shot)
    assert "a quiet room" in prompt


def test_inject_2v_reference_stage_with_refs() -> None:
    shot = {"dramatic_function": "hook", "dsl": {"environment": "a dark alley"}}
    timeline = "[0s-2s] walk begins."
    result = inject_2v_reference_stage(
        timeline, shot, ref_image_paths=["/tmp/ref.png"]
    )
    assert "=== 2V REFERENCE STAGE ===" in result
    assert "Composition prompt:" in result
    assert "Grok image model" in result
    assert "[0s-2s] walk begins." in result
    assert result.index("=== 2V REFERENCE STAGE ===") < result.index(
        "=== TIMELINE ==="
    )


def test_inject_2v_reference_stage_without_refs() -> None:
    timeline = "[0s-2s] walk begins."
    result = inject_2v_reference_stage(timeline, {}, ref_image_paths=None)
    assert result == timeline


def test_inject_2v_reference_stage_empty_list() -> None:
    timeline = "[0s-2s] walk begins."
    result = inject_2v_reference_stage(timeline, {}, ref_image_paths=[])
    assert result == timeline


def test_inject_2v_reference_stage_preserves_timeline() -> None:
    shot = {"dsl": {"environment": "a forest"}}
    timeline = "[0s-2s] action.\n[2s-5s] resolution."
    result = inject_2v_reference_stage(
        timeline, shot, ref_image_paths=["/tmp/ref.png"]
    )
    assert "[0s-2s] action." in result
    assert "[2s-5s] resolution." in result
    assert result.index("=== 2V REFERENCE STAGE ===") < result.index(
        "[0s-2s] action."
    )
