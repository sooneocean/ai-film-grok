"""P0-5: TTS language ping-pong validation (无理由 ZH→JA→ZH→JA)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from voice_cast_profiles import detect_language_pingpong  # noqa: E402


def _ev(speaker: str, lang: str, etype: str = "dialogue") -> dict:
    return {"type": etype, "speaker": speaker, "language": lang}


def test_no_issue_single_speaker_zh() -> None:
    events = [_ev("a", "zh"), _ev("a", "zh"), _ev("a", "zh")]
    assert detect_language_pingpong(events) == []


def test_block_level_switch_by_speaker_ok() -> None:
    # Different speakers carry different languages — justified by speaker layer.
    events = [_ev("a", "zh"), _ev("a", "zh"), _ev("b", "ja"), _ev("b", "ja")]
    assert detect_language_pingpong(events) == []


def test_same_speaker_flip_flagged() -> None:
    events = [_ev("a", "zh"), _ev("a", "ja"), _ev("a", "zh")]
    issues = detect_language_pingpong(events)
    codes = {i["code"] for i in issues}
    assert "TTS_LANG_FLIP_NO_SPEAKER_CHANGE" in codes


def test_pingpong_oscillation_flagged() -> None:
    events = [_ev("a", "zh"), _ev("a", "ja"), _ev("a", "zh"), _ev("a", "ja")]
    issues = detect_language_pingpong(events)
    codes = {i["code"] for i in issues}
    assert "TTS_LANG_PINGPONG" in codes


def test_narration_explicit_language_respected() -> None:
    # narration with zh stays zh; no flip if consistent
    events = [
        {"type": "narration", "speaker": "narrator", "language": "zh"},
        {"type": "narration", "speaker": "narrator", "language": "zh"},
    ]
    assert detect_language_pingpong(events) == []


def test_non_vocal_events_ignored() -> None:
    events = [
        {"type": "sfx", "speaker": "a", "language": "zh"},
        {"type": "sfx", "speaker": "a", "language": "ja"},
    ]
    assert detect_language_pingpong(events) == []
