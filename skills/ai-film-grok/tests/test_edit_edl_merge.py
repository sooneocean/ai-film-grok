"""Tests for edit_edl_merge.py — EDL merge for generated + real-footage timelines.

Previously had ZERO test coverage. This module is separate from
edit_policy.merge_edls (which IS tested by test_merge_edls.py).
These tests guard against behavioral drift between the two implementations.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_edl_merge import merge_edls  # noqa: E402


def _edl(ranges=None, sources=None, overlays=None, subtitles=None, grade=None, source_type=None):
    """Helper: build a minimal EDL dict."""
    return {
        "sources": sources or {},
        "ranges": ranges or [],
        "overlays": overlays or [],
        "subtitles": subtitles,
        "grade": grade,
        "source_type": source_type,
    }


def _range(start, end, **extra):
    return {"start": start, "end": end, **extra}


class TestMergeEdlsSequential(unittest.TestCase):
    """Non-interleave mode: append real after generated."""

    def test_two_edls_appended(self):
        gen = _edl(ranges=[_range(0, 6)], source_type="generated")
        real = _edl(ranges=[_range(0, 4)], source_type="real_footage")
        merged = merge_edls(gen, real)
        self.assertEqual(merged["segment_count"], 2)
        self.assertTrue(merged["merged"])

    def test_total_duration(self):
        gen = _edl(ranges=[_range(0, 6.0)])
        real = _edl(ranges=[_range(0, 4.0)])
        merged = merge_edls(gen, real)
        self.assertAlmostEqual(merged["total_duration_s"], 10.0, places=2)

    def test_none_inputs(self):
        merged = merge_edls(None, None)
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 0)

    def test_empty_edls(self):
        merged = merge_edls({}, {})
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 0)

    def test_only_generated(self):
        gen = _edl(ranges=[_range(0, 6)])
        merged = merge_edls(gen, None)
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 1)

    def test_only_real(self):
        real = _edl(ranges=[_range(0, 4)])
        merged = merge_edls(None, real)
        self.assertFalse(merged["merged"])
        self.assertEqual(merged["segment_count"], 1)

    def test_sources_merged(self):
        gen = _edl(sources={"clip1": "path1"}, ranges=[_range(0, 6)])
        real = _edl(sources={"footage1": "path2"}, ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertIn("clip1", merged["sources"])
        self.assertIn("footage1", merged["sources"])

    def test_overlays_concatenated(self):
        gen = _edl(overlays=[{"type": "title"}], ranges=[_range(0, 6)])
        real = _edl(overlays=[{"type": "caption"}], ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertEqual(len(merged["overlays"]), 2)


class TestMergeEdlsInterleave(unittest.TestCase):
    """Interleave mode: alternate generated/real ranges."""

    def test_interleave_alternates(self):
        gen = _edl(ranges=[_range(0, 3), _range(6, 9)])
        real = _edl(ranges=[_range(3, 6), _range(9, 12)])
        merged = merge_edls(gen, real, interleave=True)
        self.assertEqual(merged["segment_count"], 4)
        # First should be gen[0], second real[0], third gen[1], fourth real[1]
        self.assertEqual(merged["ranges"][0]["start"], 0)
        self.assertEqual(merged["ranges"][1]["start"], 3)

    def test_interleave_unequal_lengths(self):
        gen = _edl(ranges=[_range(0, 3), _range(6, 9), _range(12, 15)])
        real = _edl(ranges=[_range(3, 6)])
        merged = merge_edls(gen, real, interleave=True)
        self.assertEqual(merged["segment_count"], 4)  # 3 gen + 1 real


class TestMergeEdlsSubtitles(unittest.TestCase):
    """Hard Rule: subtitles stay last; generated wins on conflict."""

    def test_generated_subtitles_kept(self):
        gen = _edl(subtitles={"style": "yellow"}, ranges=[_range(0, 6)])
        real = _edl(subtitles={"style": "white"}, ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertEqual(merged["subtitles"]["style"], "yellow")

    def test_subtitle_conflict_flagged(self):
        gen = _edl(subtitles={"style": "a"}, ranges=[_range(0, 6)])
        real = _edl(subtitles={"style": "b"}, ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertTrue(merged["subtitle_conflict"])

    def test_no_conflict_when_only_one_has_subs(self):
        gen = _edl(subtitles={"style": "a"}, ranges=[_range(0, 6)])
        real = _edl(ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertFalse(merged["subtitle_conflict"])

    def test_hard_rules_present(self):
        merged = merge_edls(None, None)
        self.assertTrue(merged["hard_rules"]["subtitles_last"])

    def test_grade_fallback(self):
        gen = _edl(grade="cinematic", ranges=[_range(0, 6)])
        real = _edl(grade="none", ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertEqual(merged["grade"], "cinematic")

    def test_grade_from_real_when_gen_missing(self):
        gen = _edl(ranges=[_range(0, 6)])
        real = _edl(grade="warm", ranges=[_range(0, 4)])
        merged = merge_edls(gen, real)
        self.assertEqual(merged["grade"], "warm")


class TestMergeEdlsSourceTypes(unittest.TestCase):
    """source_types field tracks provenance."""

    def test_source_types_include_both(self):
        gen = _edl(ranges=[_range(0, 6)], source_type="generated")
        real = _edl(ranges=[_range(0, 4)], source_type="real_footage")
        merged = merge_edls(gen, real)
        self.assertIn("generated", merged["source_types"])
        self.assertIn("real_footage", merged["source_types"])


if __name__ == "__main__":
    unittest.main()
