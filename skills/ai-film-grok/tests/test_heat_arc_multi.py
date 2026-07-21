"""heat_scale intimacy ratio + multi-heroine lint (2026-07-21)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    apply_heat_phase_defaults,
    lint_heat_arc,
    lint_multi_heroine,
    resolve_heroine_cast_mode,
)
from film_spec import validate_film_spec  # noqa: E402


def _spine(phases: list[str]) -> list[dict]:
    df_map = {
        "setup": "hook",
        "foreplay": "sensory",
        "act": "action",
        "climax": "action",
        "afterglow": "afterglow",
        "bridge": "bridge",
    }
    shots = []
    for i, ph in enumerate(phases, 1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "dramatic_function": df_map.get(ph, "bridge"),
                "heat_phase": ph,
                "nar": "短旁白测。",
                "lipsync": False,
                "duration_sec": 6,
                "dsl": {
                    "subject": "adult woman",
                    "action": "body moves",
                    "motion": "decisive body motion continuous",
                    "story_beat": "beat",
                    "visible_change": "A to B",
                    "focal_character": "kei",
                },
            }
        )
    return shots


class HeatArcLintTests(unittest.TestCase):
    def test_max_extreme_empty_act_climax_warns(self) -> None:
        # all setup — extreme for max → soft warning only
        shots = _spine(["setup"] * 8)
        rep = lint_heat_arc(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ACT_CLIMAX_EMPTY", rep["codes"])
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertEqual(rep["sex_duration_ratio"], 0.0)

    def test_max_mid_ratio_no_forced_warning(self) -> None:
        # 2/8 act+climax by duration = 25% ≥ 20% floor; intimacy mid
        shots = _spine(
            ["setup", "setup", "setup", "foreplay", "act", "climax", "afterglow", "bridge"]
        )
        rep = lint_heat_arc(shots, heat_scale="max", advise=False)
        self.assertTrue(rep["ok"], rep)
        self.assertNotIn("HEAT_ADVISORY_INTIMACY", rep["codes"])
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.25, places=2)

    def test_max_sex_duration_below_20_warns(self) -> None:
        # only 1×6s act of 8×6s = 12.5% < 20%
        shots = _spine(
            ["setup", "setup", "setup", "foreplay", "foreplay", "act", "afterglow", "bridge"]
        )
        rep = lint_heat_arc(shots, heat_scale="max", advise=False)
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.125, places=3)
        self.assertEqual(rep["sex_duration_floor"], 0.20)

    def test_sex_duration_weighted_not_shot_count(self) -> None:
        # 1 long act (12s) + 3 setup (6s) = 12/30 = 40% sex even if shot-count is 1/4
        shots = [
            {
                "id": "shot01",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "a",
                "dsl": {"subject": "x", "action": "a", "motion": "m", "story_beat": "b", "visible_change": "c"},
            },
            {
                "id": "shot02",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "a",
                "dsl": {"subject": "x", "action": "a", "motion": "m", "story_beat": "b", "visible_change": "c"},
            },
            {
                "id": "shot03",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "a",
                "dsl": {"subject": "x", "action": "a", "motion": "m", "story_beat": "b", "visible_change": "c"},
            },
            {
                "id": "shot04",
                "heat_phase": "act",
                "dramatic_function": "action",
                "duration_sec": 12,
                "nar": "a",
                "dsl": {"subject": "x", "action": "a", "motion": "m", "story_beat": "b", "visible_change": "c"},
            },
        ]
        rep = lint_heat_arc(shots, heat_scale="max")
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.4, places=2)
        self.assertAlmostEqual(rep["sex_shot_ratio"], 0.25, places=2)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep["codes"])

    def test_hardcore_profile_raises_sex_floor(self) -> None:
        # 25% sex fails hardcore 40% floor
        shots = _spine(
            ["setup", "setup", "setup", "foreplay", "act", "climax", "afterglow", "bridge"]
        )
        rep = lint_heat_arc(
            shots, heat_scale="max", audience_profile="hardcore_male", advise=False
        )
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertEqual(rep["sex_duration_floor"], 0.40)

    def test_advise_adds_info_not_hard(self) -> None:
        shots = _spine(["setup"] * 5 + ["act", "climax", "afterglow"])
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        # may have info advisories; extreme floor may or may not warn
        self.assertTrue(any(i.get("severity") == "info" for i in rep["issues"]) or rep["ok"])

    def test_no_heat_scale_no_ratio_gate(self) -> None:
        shots = _spine(["setup"] * 8)
        rep = lint_heat_arc(shots, heat_scale=None)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["warning_count"], 0)

    def test_apply_heat_phase_defaults_no_climax_guess(self) -> None:
        shots = [
            {"id": "shot01", "dramatic_function": "hook", "nar": "x"},
            {"id": "shot02", "dramatic_function": "action", "nar": "y"},
        ]
        filled = apply_heat_phase_defaults(shots)
        self.assertEqual(len(filled), 2)
        self.assertEqual(shots[0]["heat_phase"], "setup")
        self.assertEqual(shots[1]["heat_phase"], "act")  # no auto climax


class MultiHeroineLintTests(unittest.TestCase):
    def test_single_mode_skips_lint(self) -> None:
        shots = _spine(["act", "climax"])
        rep = lint_multi_heroine(
            shots,
            cast_ids=["kei"],
            heroine_ids=["kei"],
            active=False,
            cast_mode="single",
        )
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["mode"], "single")
        self.assertEqual(rep["warning_count"], 0)

    def test_focal_gap(self) -> None:
        shots = _spine(["act", "act", "climax"])
        # all focal kei
        rep = lint_multi_heroine(
            shots,
            cast_ids=["kei", "viv", "partner"],
            heroine_ids=["kei", "viv"],
            active=True,
        )
        self.assertIn("MULTI_HEROINE_FOCAL_GAP", rep["codes"])

    def test_dual_ok(self) -> None:
        shots = _spine(["act", "climax"])
        shots[0]["dsl"]["focal_character"] = "kei"
        shots[1]["dsl"]["focal_character"] = "viv"
        shots[1]["dsl"]["viewpoint"] = "dual"
        rep = lint_multi_heroine(
            shots,
            cast_ids=["kei", "viv"],
            heroine_ids=["kei", "viv"],
            active=True,
        )
        self.assertNotIn("MULTI_HEROINE_FOCAL_GAP", rep["codes"])
        self.assertNotIn("MULTI_HEROINE_NO_DUAL", rep["codes"])


class ResolveCastModeTests(unittest.TestCase):
    def test_default_single(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="雨夜女司机色气短片",
            cast_ids=["hero", "partner"],
            cast_masters={"hero": "cast/hero-v1.png"},
        )
        self.assertEqual(r["mode"], "single")
        self.assertFalse(r["active"])

    def test_prompt_multi_with_two_masters(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="双女主 百合 两位女主办事完成",
            cast_masters={"kei": "a.png", "viv": "b.png"},
        )
        self.assertEqual(r["mode"], "multi")
        self.assertTrue(r["active"])
        self.assertGreaterEqual(len(r["heroine_ids"]), 2)

    def test_explicit_single_wins(self) -> None:
        r = resolve_heroine_cast_mode(
            cast_mode="single",
            prompt_blob="双女主",
            cast_masters={"a": "1.png", "b": "2.png"},
        )
        self.assertEqual(r["mode"], "single")

    def test_two_ref_images_plus_prompt(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="两个女人一起",
            female_ref_image_count=2,
            cast_masters={"h1": "x.png", "h2": "y.png"},
        )
        self.assertEqual(r["mode"], "multi")


class ValidateFilmSpecHeatTests(unittest.TestCase):
    def test_write_spec_does_not_auto_pin_heat_max(self) -> None:
        shots = []
        for i in range(1, 5):
            shots.append(
                {
                    "id": f"shot{i:02d}",
                    "dramatic_function": "hook",
                    "nar": "短句旁白测试。",
                    "lipsync": False,
                    "duration_sec": 6,
                    "dsl": {
                        "subject": "adult anime woman",
                        "action": "turns head slightly",
                        "motion": "fingers turn latch, body angles, continuous mid-action idle not speaking",
                        "story_beat": "looks",
                        "visible_change": "eyes open to close",
                        "camera": {"shot_size": "medium full", "angle": "eye level"},
                    },
                }
            )
        spec = {
            "title": "测不自动钉max",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            # no heat_scale
            "director_intent": {
                "logline": "成人色气测试但不强制钉档",
                "tone": "成人色气",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertNotEqual(spec.get("heat_scale"), "max")
        self.assertIn("_heat_arc", spec)
        self.assertIn("_multi_heroine", spec)

    def test_write_spec_max_sex_floor_hard_fail(self) -> None:
        # 8 setup only — max defaults sex_floor_strict → hard fail
        shots = _spine(["setup"] * 8)
        for sh in shots:
            sh["dsl"]["camera"] = {"shot_size": "medium full", "angle": "eye level"}
            sh["lipsync"] = False
        spec = {
            "title": "测性爱时长硬闸",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "director_intent": {
                "logline": "成人max但无性爱段",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        with self.assertRaises(Exception) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("SEX_DURATION", str(ctx.exception).upper())

    def test_write_spec_max_sex_floor_pass_with_enough_act(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "act", "climax", "afterglow", "bridge"]
        )
        for sh in shots:
            sh["dsl"]["camera"] = {"shot_size": "medium full", "angle": "eye level"}
            sh["lipsync"] = False
        spec = {
            "title": "测性爱时长过关",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "director_intent": {
                "logline": "成人max性爱够秒",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertGreaterEqual(spec["_heat_arc"]["sex_duration_ratio"], 0.20)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", spec["_heat_arc"]["codes"])


if __name__ == "__main__":
    unittest.main()
