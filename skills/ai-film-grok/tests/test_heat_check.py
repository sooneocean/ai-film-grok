"""Tests for heat_check.py — adult heat gate report.

Previously had ZERO test coverage. Tests cover:
  - heat_check: missing spec, valid spec, gate extraction
  - build_heat_report: historical contract report
  - _flat_shots: scene/shot flattening
  - heat_vo_suggest: VO suggestion generation
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from heat_check import _flat_shots, build_heat_report, heat_check, heat_vo_suggest  # noqa: E402


class TestFlatShots(unittest.TestCase):
    """_flat_shots extracts shot dicts from spec scenes."""

    def test_flatten_nested_shots(self):
        spec = {
            "scenes": [
                {"shots": [{"id": "s1"}, {"id": "s2"}]},
                {"shots": [{"id": "s3"}]},
            ]
        }
        shots = _flat_shots(spec)
        self.assertEqual(len(shots), 3)
        self.assertEqual(shots[0]["id"], "s1")

    def test_empty_spec(self):
        self.assertEqual(_flat_shots({}), [])

    def test_no_scenes_key(self):
        self.assertEqual(_flat_shots({"shots": []}), [])

    def test_skip_non_dict_shots(self):
        spec = {"scenes": [{"shots": [{"id": "s1"}, "invalid", 42]}]}
        shots = _flat_shots(spec)
        self.assertEqual(len(shots), 1)

    def test_skip_non_dict_scenes(self):
        spec = {"scenes": ["invalid", {"shots": [{"id": "s1"}]}]}
        shots = _flat_shots(spec)
        self.assertEqual(len(shots), 1)


class TestHeatCheck(unittest.TestCase):
    """heat_check reads film-spec.json and builds gate report."""

    def test_missing_spec(self):
        """Missing film-spec.json → ok=False with error."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = heat_check(root)
            self.assertFalse(report["ok"])
            self.assertIn("missing", report.get("error", ""))

    def test_valid_spec_with_shots(self):
        """Spec with shots → report has gate structure."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "heat_scale": "max",
                "scenes": [
                    {"shots": [
                        {"id": "s1", "heat_phase": "act", "duration_sec": 8},
                        {"id": "s2", "heat_phase": "climax", "duration_sec": 6},
                    ]}
                ],
                "director_intent": {"audience_profile": "hardcore_male"},
            }
            (root / "film-spec.json").write_text(json.dumps(spec))
            report = heat_check(root)
            self.assertIn("gates", report)
            self.assertIn("sex_duration", report["gates"])
            self.assertIn("wardrobe", report["gates"])
            self.assertIn("vo_spice", report["gates"])
            self.assertEqual(report["heat_scale"], "max")
            self.assertEqual(report["audience_profile"], "hardcore_male")
            self.assertEqual(report["shot_count"], 2)

    def test_strict_flags_extracted(self):
        """strict_flags are read from spec."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "heat_scale": "max",
                "sex_floor_strict": True,
                "sex_wardrobe_strict": True,
                "scenes": [{"shots": [{"id": "s1", "heat_phase": "act", "duration_sec": 8}]}],
            }
            (root / "film-spec.json").write_text(json.dumps(spec))
            report = heat_check(root)
            self.assertTrue(report["strict_flags"]["sex_floor_strict"])
            self.assertTrue(report["strict_flags"]["sex_wardrobe_strict"])

    def test_line_summary_present(self):
        """Report includes one-line summary string."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "heat_scale": "hot",
                "scenes": [{"shots": [{"id": "s1", "heat_phase": "act", "duration_sec": 6}]}],
            }
            (root / "film-spec.json").write_text(json.dumps(spec))
            report = heat_check(root)
            self.assertIsInstance(report.get("line"), str)
            self.assertIn("heat=hot", report["line"])

    def test_sfx_counting(self):
        """SFX shots and sound plan accents are counted."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "heat_scale": "max",
                "scenes": [{"shots": [
                    {"id": "s1", "heat_phase": "act", "duration_sec": 8, "sound_cues": [{"type": "moan"}]},
                    {"id": "s2", "heat_phase": "act", "duration_sec": 8},
                ]}],
                "sound_plan": {"events": [
                    {"type": "sfx_accent"},
                    {"type": "sfx_accent", "sex_sfx": True},
                ]},
            }
            (root / "film-spec.json").write_text(json.dumps(spec))
            report = heat_check(root)
            self.assertEqual(report["gates"]["sfx_shots"], 1)
            self.assertEqual(report["gates"]["sound_plan_accents"], 2)
            self.assertEqual(report["gates"]["sex_sfx_accents"], 1)


class TestBuildHeatReport(unittest.TestCase):
    """build_heat_report builds report from spec + shots directly."""

    def test_basic_report(self):
        spec = {"heat_scale": "max", "sex_min_duration_ratio": 0.50}
        shots = [
            {"id": "s1", "heat_phase": "act", "duration_sec": 10},
            {"id": "s2", "heat_phase": "climax", "duration_sec": 8},
        ]
        report = build_heat_report(spec, shots, total_duration_sec=60)
        self.assertIn("sex_duration_ratio", report)
        self.assertEqual(report["sex_duration_floor"], 0.50)

    def test_empty_shots(self):
        report = build_heat_report({}, [], total_duration_sec=0)
        self.assertIn("sex_duration_ratio", report)


class TestHeatVoSuggest(unittest.TestCase):
    """heat_vo_suggest generates stronger VO lines."""

    def test_missing_spec(self):
        """Missing spec → empty suggestions."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = heat_vo_suggest(root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["shots"], [])


if __name__ == "__main__":
    unittest.main()
