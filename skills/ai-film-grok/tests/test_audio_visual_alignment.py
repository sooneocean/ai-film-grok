"""P3-12: audio_visual_alignment — real AV timing alignment metrics.

Tests the new BGM cue vs shot boundary and VO onset vs cut alignment checks.
Previously this module was a 49-line stub that only checked file presence.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_visual_alignment import (  # noqa: E402
    compute_av_alignment_score,
    lint_bgm_cue_alignment,
    lint_vo_cut_alignment,
)


class TestBgmCueAlignment(unittest.TestCase):
    """BGM cue in/out should land near shot boundaries."""

    def test_cue_on_boundary_no_issue(self):
        """Cue point exactly on a shot boundary → no issue."""
        spotting = [{"label": "theme", "start_sec": 0.0, "end_sec": 6.0}]
        boundaries = [0.0, 6.0, 12.0]
        issues = lint_bgm_cue_alignment(spotting, boundaries)
        self.assertEqual(issues, [])

    def test_cue_within_tolerance_no_issue(self):
        """Cue point within tolerance of boundary → no issue."""
        spotting = [{"label": "theme", "start_sec": 0.3, "end_sec": 6.2}]
        boundaries = [0.0, 6.0, 12.0]
        issues = lint_bgm_cue_alignment(spotting, boundaries, tolerance=0.5)
        self.assertEqual(issues, [])

    def test_cue_off_boundary_triggers_issue(self):
        """Cue point far from any boundary → BGM_CUE_OFF_BOUNDARY."""
        spotting = [{"label": "theme", "start_sec": 3.0, "end_sec": 9.0}]
        boundaries = [0.0, 6.0, 12.0]
        issues = lint_bgm_cue_alignment(spotting, boundaries, tolerance=0.5)
        self.assertEqual(len(issues), 2)  # both start and end off
        codes = {i["code"] for i in issues}
        self.assertIn("BGM_CUE_OFF_BOUNDARY", codes)

    def test_empty_spotting_no_issues(self):
        issues = lint_bgm_cue_alignment([], [0.0, 6.0])
        self.assertEqual(issues, [])

    def test_no_boundaries_no_issues(self):
        """If no shot boundaries (no timeline), no alignment issues."""
        spotting = [{"label": "theme", "start_sec": 3.0}]
        issues = lint_bgm_cue_alignment(spotting, [])
        self.assertEqual(issues, [])


class TestVoCutAlignment(unittest.TestCase):
    """VO onset should align with cut points."""

    def test_vo_on_cut_no_issue(self):
        vo_entries = [{"start_sec": 0.0}, {"start_sec": 6.0}]
        boundaries = [0.0, 6.0, 12.0]
        issues = lint_vo_cut_alignment(vo_entries, boundaries)
        self.assertEqual(issues, [])

    def test_vo_off_cut_triggers_issue(self):
        vo_entries = [{"start_sec": 3.5}]
        boundaries = [0.0, 6.0, 12.0]
        issues = lint_vo_cut_alignment(vo_entries, boundaries, tolerance=0.5)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "VO_ONSET_OFF_CUT")

    def test_empty_vo_no_issues(self):
        issues = lint_vo_cut_alignment([], [0.0, 6.0])
        self.assertEqual(issues, [])


class TestAvAlignmentScore(unittest.TestCase):
    """Score computation from issue counts."""

    def test_no_issues_perfect_score(self):
        score = compute_av_alignment_score([], [], total_cues=5)
        self.assertEqual(score, 100)

    def test_issues_reduce_score(self):
        score = compute_av_alignment_score([{"code": "BGM_CUE_OFF_BOUNDARY"}], [], total_cues=5)
        self.assertLess(score, 100)

    def test_many_issues_floor_zero(self):
        many = [{"code": "BGM_CUE_OFF_BOUNDARY"}] * 20
        score = compute_av_alignment_score(many, many, total_cues=5)
        self.assertEqual(score, 0)

    def test_zero_cues_no_issues(self):
        score = compute_av_alignment_score([], [], total_cues=0)
        self.assertEqual(score, 100)


class TestBuildAlignmentReport(unittest.TestCase):
    """Integration: build_audio_visual_alignment with a film root."""

    def _make_root(self, *, timeline=None, spec=None):
        import json
        import tempfile

        tmp = tempfile.mkdtemp(prefix="aifilm_av_test_")
        root = Path(tmp)
        if timeline:
            (root / "timeline.json").write_text(
                json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
            )
        if spec:
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
        return root

    def test_report_has_av_score(self):
        """The report now includes av_alignment_score (was missing in stub)."""
        root = self._make_root(timeline={"shots": [{"id": "s1", "start_sec": 0.0, "end_sec": 6.0}]})
        from audio_visual_alignment import build_audio_visual_alignment

        rep = build_audio_visual_alignment(root, write=False)
        self.assertIn("av_alignment_score", rep)
        self.assertIsInstance(rep["av_alignment_score"], int)
        self.assertIn("shot_boundaries_count", rep)

    def test_report_schema_version_bumped(self):
        """Schema version bumped to 2 (was 1 in stub)."""
        root = self._make_root()
        from audio_visual_alignment import build_audio_visual_alignment

        rep = build_audio_visual_alignment(root, write=False)
        self.assertEqual(rep["schema_version"], 2)

    def test_bgm_off_boundary_appears_in_report(self):
        """BGM cue off boundary appears in report errors."""
        timeline = {
            "shots": [
                {"id": "s1", "start_sec": 0.0, "end_sec": 6.0},
                {"id": "s2", "start_sec": 6.0, "end_sec": 12.0},
            ]
        }
        spec = {
            "sound_plan": {"music_spotting": [{"label": "theme", "start_sec": 3.0, "end_sec": 9.0}]}
        }
        root = self._make_root(timeline=timeline, spec=spec)
        from audio_visual_alignment import build_audio_visual_alignment

        rep = build_audio_visual_alignment(root, write=False)
        bgm_issues = rep.get("bgm_cue_issues") or []
        self.assertGreater(len(bgm_issues), 0)
        codes = {i["code"] for i in bgm_issues}
        self.assertIn("BGM_CUE_OFF_BOUNDARY", codes)
        self.assertLess(rep["av_alignment_score"], 100)

    def test_aligned_cues_perfect_score(self):
        """Aligned BGM cues → perfect score."""
        timeline = {
            "shots": [
                {"id": "s1", "start_sec": 0.0, "end_sec": 6.0},
                {"id": "s2", "start_sec": 6.0, "end_sec": 12.0},
            ]
        }
        spec = {
            "sound_plan": {
                "music_spotting": [{"label": "theme", "start_sec": 0.0, "end_sec": 12.0}]
            }
        }
        root = self._make_root(timeline=timeline, spec=spec)
        from audio_visual_alignment import build_audio_visual_alignment

        rep = build_audio_visual_alignment(root, write=False)
        bgm_issues = rep.get("bgm_cue_issues") or []
        self.assertEqual(bgm_issues, [])
        self.assertEqual(rep["av_alignment_score"], 100)


if __name__ == "__main__":
    unittest.main()
