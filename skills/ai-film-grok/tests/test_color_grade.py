#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from color_grade import (  # noqa: E402
    PRESETS,
    ColorGradeError,
    build_ffmpeg_filter,
    list_presets,
    plan_shot_grades,
)
from util import write_json  # noqa: E402


class ColorGradeTests(unittest.TestCase):
    def test_list_presets(self) -> None:
        names = list_presets()
        self.assertIn("none", names)
        self.assertIn("warm_cinematic", names)
        self.assertIn("cool_steel", names)

    def test_build_filter_preset(self) -> None:
        """DoD: preset → ffmpeg eq filter chain."""
        f = build_ffmpeg_filter("warm_cinematic")
        self.assertIn("eq=", f)
        self.assertIn("contrast=", f)
        self.assertIn("saturation=", f)

    def test_build_filter_none_is_passthrough(self) -> None:
        f = build_ffmpeg_filter("none")
        self.assertIn("eq=", f)
        # none → slope 1.0, offset 0 → neutral eq
        self.assertIn("contrast=1.0000", f)

    def test_build_filter_raw_passthrough(self) -> None:
        """Raw ffmpeg filter strings pass through unchanged."""
        raw = "eq=contrast=1.2:brightness=0.05"
        self.assertEqual(build_ffmpeg_filter(raw), raw)

    def test_build_filter_unknown_raises(self) -> None:
        with self.assertRaises(ColorGradeError):
            build_ffmpeg_filter("nonexistent_preset")

    def test_build_filter_dict_cdl(self) -> None:
        """Dict CDL input works."""
        cdl = {
            "slope": [1.1, 1.0, 0.9],
            "offset": [0.01, 0.0, -0.01],
            "power": [1.0, 1.0, 1.0],
            "saturation": 0.95,
        }
        f = build_ffmpeg_filter(cdl)
        self.assertIn("eq=", f)

    def test_plan_shot_grades_from_palette(self) -> None:
        """DoD: plan maps cinema_prompt palette → grade preset."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "title": "t",
                "scenes": [
                    {
                        "id": "s1",
                        "shots": [
                            {"id": "sh1", "dsl": {"palette": "teal_orange"}},
                            {"id": "sh2", "dsl": {"palette": "cool_steel"}},
                            {"id": "sh3", "dsl": {}},
                        ],
                    }
                ],
            }
            write_json(root / "film-spec.json", spec)
            receipt = plan_shot_grades(root)
            self.assertTrue(receipt["ok"])
            self.assertEqual(len(receipt["shots"]), 3)
            self.assertEqual(receipt["shots"][0]["grade_preset"], "warm_cinematic")
            self.assertEqual(receipt["shots"][1]["grade_preset"], "cool_steel")
            self.assertEqual(receipt["shots"][2]["grade_preset"], "none")
            self.assertTrue(receipt["shots"][0]["filter"].startswith("eq="))

    def test_plan_missing_spec_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ColorGradeError):
                plan_shot_grades(Path(tmp))

    def test_presets_have_required_fields(self) -> None:
        for name, p in PRESETS.items():
            self.assertIn("slope", p)
            self.assertIn("offset", p)
            self.assertIn("power", p)
            self.assertIn("saturation", p)
            self.assertEqual(len(p["slope"]), 3)


if __name__ == "__main__":
    unittest.main()
