"""Tests for BGM spotting beat alignment verification.

Verifies:
- MUSIC_SPOT_INVALID_RANGE: end_sec <= start_sec
- MUSIC_SPOT_OUT_OF_RANGE: segment extends beyond total_duration
- MUSIC_SPOT_BEAT_REF_INVALID: beat_ref not found in beats
- MUSIC_SPOT_OVERLAP: overlapping segments
- No issues when segments are clean and aligned
- Empty music_spotting → ok
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rhythm import verify_music_spotting


class TestMusicSpottingVerification:
    """verify_music_spotting checks BGM spotting alignment."""

    def test_invalid_range_detected(self):
        spotting = [
            {"label": "bad", "start_sec": 10.0, "end_sec": 5.0},
        ]
        result = verify_music_spotting(spotting)
        assert "MUSIC_SPOT_INVALID_RANGE" in result["codes"]

    def test_out_of_range_detected(self):
        spotting = [
            {"label": "over", "start_sec": 25.0, "end_sec": 35.0},
        ]
        result = verify_music_spotting(spotting, total_duration=30.0)
        assert "MUSIC_SPOT_OUT_OF_RANGE" in result["codes"]

    def test_beat_ref_invalid_detected(self):
        spotting = [
            {"label": "theme", "start_sec": 0.0, "end_sec": 10.0, "beat_ref": "bt_nonexistent"},
        ]
        beats = [{"id": "bt_001"}, {"id": "bt_002"}]
        result = verify_music_spotting(spotting, beats=beats)
        assert "MUSIC_SPOT_BEAT_REF_INVALID" in result["codes"]

    def test_beat_ref_valid_no_issue(self):
        spotting = [
            {"label": "theme", "start_sec": 0.0, "end_sec": 10.0, "beat_ref": "bt_001"},
        ]
        beats = [{"id": "bt_001"}, {"id": "bt_002"}]
        result = verify_music_spotting(spotting, beats=beats)
        assert "MUSIC_SPOT_BEAT_REF_INVALID" not in result["codes"]

    def test_overlap_detected(self):
        spotting = [
            {"label": "a", "start_sec": 0.0, "end_sec": 15.0},
            {"label": "b", "start_sec": 10.0, "end_sec": 20.0},
        ]
        result = verify_music_spotting(spotting)
        assert "MUSIC_SPOT_OVERLAP" in result["codes"]

    def test_no_overlap_no_issue(self):
        spotting = [
            {"label": "a", "start_sec": 0.0, "end_sec": 10.0},
            {"label": "b", "start_sec": 10.0, "end_sec": 20.0},
        ]
        result = verify_music_spotting(spotting)
        assert result["ok"] is True

    def test_empty_spotting_ok(self):
        result = verify_music_spotting([])
        assert result["ok"] is True

    def test_clean_segments_ok(self):
        spotting = [
            {
                "label": "intro",
                "start_sec": 0.0,
                "end_sec": 8.0,
                "beat_ref": "bt_001",
                "fade_in_sec": 1.0,
            },
            {"label": "build", "start_sec": 8.0, "end_sec": 20.0, "beat_ref": "bt_002"},
            {
                "label": "outro",
                "start_sec": 20.0,
                "end_sec": 28.0,
                "beat_ref": "bt_003",
                "fade_out_sec": 2.0,
            },
        ]
        beats = [{"id": "bt_001"}, {"id": "bt_002"}, {"id": "bt_003"}]
        result = verify_music_spotting(spotting, beats=beats, total_duration=30.0)
        assert result["ok"] is True

    def test_segments_checked_count(self):
        spotting = [
            {"label": "a", "start_sec": 0.0, "end_sec": 5.0},
            {"label": "b", "start_sec": 5.0, "end_sec": 10.0},
            {"label": "c", "start_sec": 10.0, "end_sec": 15.0},
        ]
        result = verify_music_spotting(spotting)
        assert result["segments_checked"] == 3
