"""2026-08-07 heat plot-driven policy: explicit max only; adult default = hot."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from story_plan import (  # noqa: E402
    build_planned_graph,
    derive_heat_scale,
    detect_heat_signals,
    normalize_story,
    project_graph_to_film_spec,
)


class PlotDrivenHeatTests(unittest.TestCase):
    def test_empty_adult_default_is_hot_not_max(self) -> None:
        norm = normalize_story("雨夜出租车里的一次对话", title_hint="雨夜")
        self.assertEqual(norm["genre"], "adult")
        h = norm["heat_signals"]
        self.assertEqual(h["heat_scale"], "hot")
        self.assertEqual(h["pinned_by"], "plot_driven")
        self.assertFalse(h.get("evidence_max"))

    def test_explicit_max_markers(self) -> None:
        h = detect_heat_signals("尺度拉到最高，办事戏完整")
        self.assertEqual(h["heat_scale"], "max")
        self.assertEqual(h["pinned_by"], "explicit_max")
        self.assertTrue(h["evidence_max"])

    def test_adult_intensity_is_hot(self) -> None:
        h = detect_heat_signals("成人色气短片，暧昧缠绵")
        self.assertEqual(h["heat_scale"], "hot")
        self.assertEqual(h["pinned_by"], "plot_driven")

    def test_derive_three_state(self) -> None:
        self.assertEqual(derive_heat_scale({"heat_scale": "soft"}, genre="adult"), ("soft", "user_soft"))
        self.assertEqual(
            derive_heat_scale({"heat_scale": "max", "evidence_max": True}, genre="adult"),
            ("max", "explicit_max"),
        )
        self.assertEqual(derive_heat_scale({}, genre="adult"), ("hot", "plot_driven"))

    def test_project_plot_driven_no_challenge_max(self) -> None:
        norm = normalize_story("雨夜书店两人靠近", title_hint="雨夜")
        graph = build_planned_graph(norm, target_duration=40.0)
        spec = project_graph_to_film_spec(graph, normalized=norm)
        self.assertEqual(spec.get("heat_scale"), "hot")
        self.assertEqual(spec.get("heat_pinned_by"), "plot_driven")
        self.assertIsNot(spec.get("challenge_max_scale"), True)
        self.assertIs(spec.get("sex_floor_strict"), False)

    def test_project_explicit_max_keeps_iron(self) -> None:
        norm = normalize_story("成人办事：尺度拉满落锁加演", title_hint="拉满")
        self.assertEqual(norm["heat_signals"]["heat_scale"], "max")
        graph = build_planned_graph(norm, target_duration=40.0)
        spec = project_graph_to_film_spec(graph, normalized=norm)
        self.assertEqual(spec.get("heat_scale"), "max")
        self.assertTrue(spec.get("challenge_max_scale"))
        self.assertTrue(spec.get("sex_floor_strict"))


if __name__ == "__main__":
    unittest.main()
