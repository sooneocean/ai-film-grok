#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import merge_edls  # noqa: E402


def _gen_edl():
    return {
        "version": 1,
        "sources": {"sh1": "/clips/sh1.mp4", "sh2": "/clips/sh2.mp4"},
        "ranges": [
            {"source": "sh1", "start": 0.0, "end": 5.0, "beat": "hook"},
            {"source": "sh2", "start": 0.0, "end": 4.0, "beat": "reaction"},
        ],
        "grade": "none",
        "overlays": [],
        "subtitles": "/subs/master.srt",
        "source_type": "generated",
    }


def _real_edl():
    return {
        "version": 1,
        "sources": {"src1": "/footage/raw/src1.mp4"},
        "ranges": [
            {"source": "src1", "start": 0.0, "end": 3.0, "beat": "segment_1"},
            {"source": "src1", "start": 3.5, "end": 7.0, "beat": "segment_2"},
        ],
        "grade": "warm_cinematic",
        "overlays": [],
        "subtitles": "/footage/edit/master.srt",
        "source_type": "real_footage",
    }


class MergeEdlsTests(unittest.TestCase):
    def test_sequential_merge(self) -> None:
        """DoD: real ranges appended after generated."""
        merged = merge_edls(_gen_edl(), _real_edl())
        self.assertTrue(merged["merged"])
        self.assertEqual(merged["segment_count"], 4)
        self.assertEqual(len(merged["sources"]), 3)

    def test_subtitles_last_rule(self) -> None:
        """Hard Rule 1: generated subtitles kept; conflict flagged."""
        merged = merge_edls(_gen_edl(), _real_edl())
        self.assertTrue(merged["hard_rules"]["subtitles_last"])
        self.assertTrue(merged["subtitle_conflict"])
        # generated subtitles win
        self.assertEqual(merged["subtitles"], "/subs/master.srt")

    def test_interleave(self) -> None:
        merged = merge_edls(_gen_edl(), _real_edl(), interleave=True)
        self.assertEqual(merged["segment_count"], 4)
        # first range is generated (gen comes first in interleave)
        self.assertEqual(merged["ranges"][0]["source"], "sh1")
        self.assertEqual(merged["ranges"][1]["source"], "src1")

    def test_merge_only_generated(self) -> None:
        merged = merge_edls(_gen_edl(), None)
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 2)

    def test_merge_only_real(self) -> None:
        merged = merge_edls(None, _real_edl())
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 2)

    def test_total_duration(self) -> None:
        merged = merge_edls(_gen_edl(), _real_edl())
        self.assertGreater(merged["total_duration_s"], 0)

    def test_overlays_combined(self) -> None:
        gen = _gen_edl()
        gen["overlays"] = [{"file": "/anim1.mp4", "start_in_output": 0.0, "duration": 5.0}]
        real = _real_edl()
        real["overlays"] = [{"file": "/anim2.mp4", "start_in_output": 0.0, "duration": 3.0}]
        merged = merge_edls(gen, real)
        self.assertEqual(len(merged["overlays"]), 2)

    def test_empty_both(self) -> None:
        merged = merge_edls(None, None)
        self.assertEqual(merged["segment_count"], 0)
        self.assertFalse(merged["merged"])


if __name__ == "__main__":
    unittest.main()
