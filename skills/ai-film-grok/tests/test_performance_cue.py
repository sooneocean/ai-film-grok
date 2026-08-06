from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from performance_cue import (  # noqa: E402
    PerformanceCueError,
    compile_edge,
    compile_instruction,
    cue_hash,
    normalize_performance_cue,
    summarize_bgm_response,
)


def test_cue_normalizes_and_is_reproducible() -> None:
    cue = normalize_performance_cue(
        {
            "emotion": "teasing",
            "intensity": 0.72,
            "rate": "+6%",
            "pitch": "+2st",
            "volume": "-3%",
            "delivery": ["breathy", "breathy", "whisper_start"],
            "pauses_ms": [180, 320],
            "take_seed": 42,
        }
    )
    assert cue["delivery"] == ["breathy", "whisper_start"]
    assert cue_hash(cue) == cue_hash(cue)
    assert "Emotion: teasing" in compile_instruction(cue)


def test_edge_compiler_keeps_unsupported_delivery_auditable() -> None:
    compiled = compile_edge(
        normalize_performance_cue({"delivery": ["crying"], "pauses_ms": [700]}),
        "她回头。",
    )
    assert compiled["rate"] == "+0%"
    assert compiled["pitch"] == "+0Hz"
    assert compiled["unsupported"] == ["crying"]
    assert "prosody" in compiled["ssml"]


def test_invalid_cue_fails_closed() -> None:
    with pytest.raises(PerformanceCueError):
        normalize_performance_cue({"intensity": 1.5})


def test_bgm_response_is_explainable_and_intensity_driven() -> None:
    quiet = summarize_bgm_response([{"performance_cue": {"intensity": 0.1}}])
    intense = summarize_bgm_response([{"performance_cue": {"intensity": 0.9}}])
    assert intense["music_gain"] < quiet["music_gain"]
    assert intense["duck_db"] < quiet["duck_db"]
    assert intense["tail_ms"] > quiet["tail_ms"]
