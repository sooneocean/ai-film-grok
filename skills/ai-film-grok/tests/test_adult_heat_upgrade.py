"""P0 adult upgrade: spines, coitus grammar, size ladder, motion templates (2026-07-22)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    coverage_defaults_for_heat,
    i2v_motion_templates,
    lint_coitus_grammar,
    lint_heat_arc,
    lint_size_ladder,
    shot_coitus_readable,
)
from story_plan import (  # noqa: E402
    build_planned_graph,
    detect_heat_signals,
    normalize_story,
    project_graph_to_film_spec,
    select_beat_spine,
)


class HeatSignalTests(unittest.TestCase):
    def test_no_pin_without_evidence(self) -> None:
        h = detect_heat_signals("雨夜出租车里的一次对话")
        self.assertIsNone(h["heat_scale"])
        self.assertEqual(h["spine"], "default")

    def test_adult_max_from_brief(self) -> None:
        h = detect_heat_signals("成人办事短剧，尺度拉满，落锁加演")
        self.assertEqual(h["heat_scale"], "max")
        self.assertEqual(h["spine"], "adult_max")
        self.assertFalse(h["hardcore"])

    def test_hardcore_male(self) -> None:
        h = detect_heat_signals("重口男向，尺度太小不够色")
        self.assertEqual(h["heat_scale"], "max")
        self.assertTrue(h["hardcore"])
        self.assertEqual(h["audience_profile"], "hardcore_male")


class AdultSpineTests(unittest.TestCase):
    def test_adult_spine_has_act_climax(self) -> None:
        spine = select_beat_spine({"heat_scale": "max", "spine": "adult_max"})
        phases = [b.get("heat_phase") for b in spine]
        self.assertIn("act", phases)
        self.assertIn("climax", phases)
        self.assertIn("foreplay", phases)
        beats = {b.get("coitus_beat") for b in spine}
        self.assertIn("union", beats)
        self.assertIn("rhythm", beats)
        self.assertIn("finish", beats)

    def test_plan_projects_heat_fields(self) -> None:
        raw = "成人办事：展厅落锁卸甲跨坐沉腰办穿，下一场换你顶。"
        norm = normalize_story(raw, title_hint="落锁加演")
        self.assertEqual(norm["heat_signals"]["heat_scale"], "max")
        graph = build_planned_graph(norm, target_duration=55.0)
        spec = project_graph_to_film_spec(graph, normalized=norm)
        self.assertEqual(spec.get("heat_scale"), "max")
        self.assertTrue(spec.get("coitus_grammar", {}).get("enabled"))
        shots = []
        for sc in spec.get("scenes") or []:
            shots.extend(sc.get("shots") or [])
        self.assertGreaterEqual(len(shots), 6)
        has_act = any(s.get("heat_phase") == "act" for s in shots)
        self.assertTrue(has_act)
        has_cb = any(s.get("coitus_beat") == "rhythm" for s in shots)
        self.assertTrue(has_cb)
        rep = lint_heat_arc(
            shots,
            heat_scale="max",
            coitus_grammar=spec.get("coitus_grammar"),
        )
        self.assertGreaterEqual(rep["sex_duration_ratio"], 0.20, rep)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep["codes"])


class CoitusLintTests(unittest.TestCase):
    def test_readable_pose(self) -> None:
        shot = {
            "id": "s1",
            "heat_phase": "act",
            "dsl": {"action": "straddle-seat hips-sink grind", "motion": "hips-sink twice"},
        }
        self.assertTrue(shot_coitus_readable(shot))

    def test_hardcore_missing_beats_warns(self) -> None:
        shots = [
            {
                "id": "a",
                "heat_phase": "act",
                "duration_sec": 8,
                "dsl": {"action": "straddle hips-sink", "motion": "grind"},
            },
            {
                "id": "b",
                "heat_phase": "climax",
                "duration_sec": 8,
                "dsl": {"action": "arch-finish", "motion": "residual-tremor"},
            },
        ]
        rep = lint_coitus_grammar(
            shots,
            heat_scale="max",
            audience_profile="hardcore_male",
            coitus_grammar={"enabled": True},
        )
        self.assertIn("COITUS_BEAT_MISSING", rep["codes"])

    def test_plain_max_without_enabled_ok(self) -> None:
        shots = [
            {
                "id": "a",
                "heat_phase": "act",
                "duration_sec": 6,
                "dsl": {"action": "straddle hips-sink", "motion": "grind"},
            },
            {
                "id": "b",
                "heat_phase": "climax",
                "duration_sec": 6,
                "dsl": {"action": "arch-finish", "motion": "tremor"},
            },
        ]
        rep = lint_coitus_grammar(shots, heat_scale="max", coitus_grammar=None)
        self.assertNotIn("COITUS_BEAT_MISSING", rep["codes"])


class SizeLadderTests(unittest.TestCase):
    def test_flat_triple_hardcore(self) -> None:
        shots = []
        for i in range(6):
            shots.append(
                {
                    "id": f"s{i}",
                    "heat_phase": "act" if i > 2 else "setup",
                    "dsl": {"camera": {"shot_size": "medium"}},
                }
            )
        rep = lint_size_ladder(shots, heat_scale="max", audience_profile="hardcore_male")
        self.assertIn("SIZE_STACK_FLAT", rep["codes"])


class MotionTemplateTests(unittest.TestCase):
    def test_sex_templates_exist(self) -> None:
        t = i2v_motion_templates()
        for k in ("rhythm_hips", "union_settle", "finish_arch", "undress_slide"):
            self.assertIn(k, t)
            self.assertTrue(len(t[k]) > 20)

    def test_heat_coverage_overrides_action(self) -> None:
        d = coverage_defaults_for_heat("action", heat_phase="act", coitus_beat="rhythm")
        self.assertIn("hips", d["motion"].lower())
        self.assertEqual(d["motion_key"], "rhythm_hips")


class SexSfxAndPilotTests(unittest.TestCase):
    def test_sex_sfx_inject(self) -> None:
        from sound_plan import inject_sex_sfx_from_shots

        shots = [
            {
                "id": "s1",
                "heat_phase": "act",
                "sound_cues": ["impact", "breath"],
            },
            {"id": "s2", "heat_phase": "setup"},
        ]
        plan = {"mood": "rnb", "bed": True, "events": []}
        out = inject_sex_sfx_from_shots(plan, shots, heat_scale="max")
        assert out is not None
        accents = [e for e in out["events"] if e.get("type") == "sfx_accent"]
        self.assertEqual(len(accents), 2)
        sex_accents = [a for a in accents if a.get("sex_sfx")]
        self.assertEqual(len(sex_accents), 1)
        self.assertEqual(sex_accents[0]["shot_id"], "s1")
        self.assertEqual(sex_accents[0]["kind"], "impact")
        self.assertTrue(sex_accents[0].get("sex_sfx"))

    def test_pilot_prefers_adult_coitus(self) -> None:
        from pilot_review import pick_pilot_shots

        spec = {
            "heat_scale": "max",
            "scenes": [
                {
                    "shots": [
                        {"id": "hook", "dramatic_function": "hook", "coitus_beat": "entry"},
                        {"id": "und", "dramatic_function": "sensory", "coitus_beat": "undress"},
                        {"id": "uni", "dramatic_function": "action", "coitus_beat": "union"},
                        {"id": "rhy", "dramatic_function": "action", "coitus_beat": "rhythm"},
                        {"id": "fin", "dramatic_function": "action", "coitus_beat": "finish"},
                    ]
                }
            ],
        }
        picked = pick_pilot_shots(spec, n=3)
        self.assertEqual(picked, ["und", "uni", "rhy"])

    def test_dual_climax_spine(self) -> None:
        from story_plan import detect_heat_signals, select_beat_spine

        h = detect_heat_signals("成人双高潮两轮办事")
        self.assertTrue(h.get("dual_climax"))
        spine = select_beat_spine(h)
        keys = [b["key"] for b in spine]
        self.assertIn("climax1", keys)
        self.assertIn("union2", keys)
        self.assertIn("climax2", keys)


class SpiceExtremeTests(unittest.TestCase):
    def test_extreme_too_mild(self) -> None:
        from edit_policy import lint_sex_vo_spice

        shots = [
            {
                "id": "a",
                "heat_phase": "act",
                "nar": "规矩失效。加演一场。",  # dual-entendre only
                "dsl": {"action": "straddle hips-sink", "motion": "grind"},
            },
            {
                "id": "b",
                "heat_phase": "climax",
                "nar": "夜色温柔。故事未完。",
                "dsl": {"action": "arch-finish", "motion": "tremor"},
            },
        ]
        rep = lint_sex_vo_spice(
            shots, heat_scale="max", spice_level="extreme", audience_profile="hardcore_male"
        )
        self.assertIn("HEAT_VO_SPICE_TOO_MILD", rep["codes"])

    def test_sex_floor_default_50(self) -> None:
        from edit_policy import DEFAULT_SEX_DURATION_FLOOR

        self.assertAlmostEqual(DEFAULT_SEX_DURATION_FLOOR, 0.50, places=2)

    def test_pose_variety_and_montage(self) -> None:
        from edit_policy import lint_montage_craft, lint_sex_pose_variety

        shots = [
            {
                "id": f"a{i}",
                "heat_phase": "act",
                "sex_pose": "straddle",
                "dsl": {"action": "straddle hips-sink same", "motion": "grind"},
            }
            for i in range(3)
        ]
        rep = lint_sex_pose_variety(shots, heat_scale="max", audience_profile="hardcore_male")
        self.assertIn("SEX_POSE_STALE", rep["codes"])
        m = lint_montage_craft(
            ["cut_on_action", "cut_on_action", "cut_on_action"],
            heat_scale="max",
            audience_profile="hardcore_male",
            shot_count=8,
        )
        self.assertIn("MONTAGE_FLAT", m["codes"])


if __name__ == "__main__":
    unittest.main()
