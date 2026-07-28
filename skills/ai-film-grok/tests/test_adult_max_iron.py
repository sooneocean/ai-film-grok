#!/usr/bin/env python3
"""Adult max IRON (2026-07-24): meat ratio / undress / bare peak / spice extreme."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    DEFAULT_SEX_DURATION_FLOOR,
    EXTREME_INTIMACY_FLOOR,
    HARDCORE_SEX_DURATION_TARGET,
    apply_wardrobe_continuity,
    lint_heat_arc,
    lint_sex_arc,
    lint_sex_wardrobe,
    normalize_spice_level,
)
from story_plan import detect_heat_signals  # noqa: E402


class AdultMaxIronConstants(unittest.TestCase):
    def test_floors(self) -> None:
        self.assertEqual(DEFAULT_SEX_DURATION_FLOOR, 0.50)
        self.assertEqual(HARDCORE_SEX_DURATION_TARGET, 0.55)
        self.assertEqual(EXTREME_INTIMACY_FLOOR, 0.60)

    def test_spice_max_is_extreme(self) -> None:
        self.assertEqual(normalize_spice_level(None, heat_scale="max"), "extreme")


class AdultMaxIronHeatSignals(unittest.TestCase):
    def test_adult_markers_pin_max(self) -> None:
        h = detect_heat_signals("成人里番办事脱衣高潮")
        self.assertEqual(h["heat_scale"], "max")
        self.assertEqual(h["spice_level"], "extreme")
        self.assertTrue(h["evidence_max"])

    def test_cooldown_wins(self) -> None:
        h = detect_heat_signals("heat_scale=soft 全年龄")
        self.assertEqual(h["heat_scale"], "soft")
        self.assertFalse(h["evidence_max"])


class AdultMaxIronWardrobe(unittest.TestCase):
    def test_phase_escalate_act_and_climax(self) -> None:
        shots = [
            {
                "id": "s01",
                "heat_phase": "setup",
                "wardrobe_state": "full",
                "duration_sec": 4,
            },
            {
                "id": "s02",
                "heat_phase": "foreplay",
                "wardrobe_state": "full",
                "dsl": {"action": "removes armor strips undress"},
                "duration_sec": 5,
            },
            {
                "id": "s03",
                "heat_phase": "act",
                "wardrobe_state": "partial",
                "duration_sec": 8,
            },
            {
                "id": "s04",
                "heat_phase": "climax",
                "wardrobe_state": "undressed",
                "duration_sec": 8,
            },
        ]
        cont = apply_wardrobe_continuity(shots, heat_scale="max")
        self.assertTrue(cont.get("auto_escalate"))
        # act raised to undressed, climax to bare
        self.assertEqual(shots[2].get("wardrobe_state"), "undressed")
        self.assertEqual(shots[3].get("wardrobe_state"), "bare")
        self.assertEqual(cont.get("final_peak"), "bare")
        self.assertTrue(cont.get("escalated"))

    def test_bare_peak_missing_without_bare(self) -> None:
        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "undressed",
                "dsl": {"action": "strips hips-sink", "subject": "undressed bare skin"},
                "duration_sec": 10,
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "wardrobe_state": "undressed",
                "dsl": {"action": "arch-finish", "subject": "undressed"},
                "duration_sec": 10,
            },
        ]
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertIn("HEAT_BARE_PEAK_MISSING", rep.get("codes", []))

    def test_bare_peak_ok(self) -> None:
        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "undressed",
                "dsl": {
                    "action": "removes strips hips-sink",
                    "subject": "undressed bare skin",
                },
                "duration_sec": 10,
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "wardrobe_state": "bare",
                "dsl": {"action": "arch-finish", "subject": "bare exposed"},
                "duration_sec": 10,
            },
        ]
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertNotIn("HEAT_BARE_PEAK_MISSING", rep.get("codes", []))
        self.assertTrue(rep.get("bare_peak_ok"))

    def test_partial_act_is_weak_on_max(self) -> None:
        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "partial",
                "dsl": {"action": "hips-sink", "subject": "partial open shirt"},
                "duration_sec": 10,
            },
        ]
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertIn("HEAT_SEX_WARDROBE_WEAK", rep.get("codes", []))


class AdultMaxIronContinuousChallenge(unittest.TestCase):
    def test_regression_before_climax(self) -> None:
        from edit_policy import lint_heat_escalation_challenge

        shots = [
            {"id": "a", "heat_phase": "act", "duration_sec": 6},
            {"id": "b", "heat_phase": "foreplay", "duration_sec": 6},  # 泄火
            {"id": "c", "heat_phase": "climax", "duration_sec": 6},
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertIn("HEAT_ESCALATION_REGRESSION", rep.get("codes", []))

    def test_setup_after_act(self) -> None:
        from edit_policy import lint_heat_escalation_challenge

        shots = [
            {"id": "a", "heat_phase": "act", "duration_sec": 6},
            {"id": "s", "heat_phase": "setup", "duration_sec": 6},
            {"id": "c", "heat_phase": "climax", "duration_sec": 6},
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertIn("HEAT_ESCALATION_REGRESSION", rep.get("codes", []))

    def test_monotonic_rise_ok(self) -> None:
        from edit_policy import lint_heat_escalation_challenge

        shots = [
            {"id": "s", "heat_phase": "setup", "duration_sec": 4},
            {"id": "f", "heat_phase": "foreplay", "duration_sec": 5},
            {"id": "a1", "heat_phase": "act", "duration_sec": 8},
            {"id": "a2", "heat_phase": "act", "duration_sec": 8},
            {"id": "a3", "heat_phase": "act", "duration_sec": 8},
            {"id": "c", "heat_phase": "climax", "duration_sec": 8},
            {"id": "g", "heat_phase": "afterglow", "duration_sec": 4},
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertTrue(rep.get("ok"), rep)
        self.assertNotIn("HEAT_ESCALATION_REGRESSION", rep.get("codes", []))

    def test_foreplay_stall(self) -> None:
        from edit_policy import lint_heat_escalation_challenge

        shots = [
            {"id": f"f{i}", "heat_phase": "foreplay", "duration_sec": 6} for i in range(4)
        ]
        shots.append({"id": "a", "heat_phase": "act", "duration_sec": 6})
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertIn("HEAT_ESCALATION_STALL", rep.get("codes", []))

    def test_act_without_climax(self) -> None:
        from edit_policy import lint_heat_escalation_challenge

        shots = [
            {"id": f"a{i}", "heat_phase": "act", "duration_sec": 6} for i in range(6)
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertIn("HEAT_ESCALATION_NO_PEAK", rep.get("codes", []))


class AdultMaxIronSexArc(unittest.TestCase):
    def test_missing_penetration_flags(self) -> None:
        shots = [
            {"id": "f1", "heat_phase": "foreplay", "duration_sec": 6, "dsl": {"action": "kiss caress"}},
            {
                "id": "a1",
                "heat_phase": "act",
                "duration_sec": 10,
                "dsl": {"action": "embrace hug lean soft"},
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "duration_sec": 8,
                "dsl": {"action": "arch-finish residual tremor 高潮"},
            },
        ]
        rep = lint_sex_arc(shots, heat_scale="max")
        self.assertIn("SEX_ARC_PENETRATION_MISSING", rep.get("codes", []))

    def test_bare_hug_not_penetration(self) -> None:
        """裸抱无办事动词不得假绿 penetration。"""
        shots = [
            {
                "id": "f1",
                "heat_phase": "foreplay",
                "duration_sec": 6,
                "wardrobe_state": "partial",
                "dsl": {"action": "undress strips"},
            },
            {
                "id": "a1",
                "heat_phase": "act",
                "duration_sec": 12,
                "wardrobe_state": "bare",
                "dsl": {"action": "embrace hug soft lean", "subject": "bare skin hug"},
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "duration_sec": 8,
                "wardrobe_state": "bare",
                "dsl": {"action": "smile soft hold"},
            },
        ]
        rep = lint_sex_arc(shots, heat_scale="max")
        self.assertFalse(rep.get("has_penetration"))
        self.assertIn("SEX_ARC_PENETRATION_MISSING", rep.get("codes", []))
        self.assertIn("SEX_ARC_PENETRATION_VERB_WEAK", rep.get("codes", []))
        codes = set(rep.get("codes") or [])
        self.assertTrue(
            "SEX_ARC_RELEASE_MARKER_WEAK" in codes
            or "SEX_ARC_CLIMAX_RELEASE_MISSING" in codes,
            codes,
        )
        self.assertFalse(rep.get("has_climax_release"))

    def test_full_arc_ok(self) -> None:
        shots = [
            {
                "id": "f1",
                "heat_phase": "foreplay",
                "duration_sec": 6,
                "dsl": {"action": "strips undress shoulder"},
            },
            {
                "id": "a1",
                "heat_phase": "act",
                "duration_sec": 10,
                "dsl": {"action": "straddle hips-sink thrust 沉腰"},
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "duration_sec": 8,
                "dsl": {"action": "arch-finish 高潮 射出"},
            },
        ]
        rep = lint_sex_arc(shots, heat_scale="max")
        self.assertTrue(rep.get("ok"), rep)
        self.assertTrue(rep.get("has_foreplay"))
        self.assertTrue(rep.get("has_penetration"))
        self.assertTrue(rep.get("has_climax_release"))

    def test_detail_cu_missing(self) -> None:
        from edit_policy import lint_sex_detail_cu

        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "duration_sec": 10,
                "dsl": {
                    "action": "hips-sink thrust",
                    "camera": {"shot_size": "medium"},
                },
            },
        ]
        rep = lint_sex_detail_cu(shots, heat_scale="max")
        self.assertIn("SEX_DETAIL_CU_MISSING", rep.get("codes", []))

    def test_detail_cu_ok(self) -> None:
        from edit_policy import lint_sex_detail_cu

        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "coverage_role": "detail",
                "framing": "union_closeup",
                "duration_sec": 8,
                "dsl": {
                    "action": "hips-sink pelvis-lock",
                    "camera": {"shot_size": "close-up insert"},
                },
            },
        ]
        rep = lint_sex_detail_cu(shots, heat_scale="max")
        self.assertTrue(rep.get("ok"), rep)
        self.assertIn("a1", rep.get("detail_shots") or [])

    def test_partner_wardrobe_weak(self) -> None:
        from edit_policy import lint_both_undress

        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "partner_wardrobe_state": "full",
                "duration_sec": 10,
                "dsl": {"action": "hips-sink thrust straddle"},
            },
        ]
        rep = lint_both_undress(shots, heat_scale="max")
        self.assertIn("SEX_BOTH_UNDRESS_MISSING", rep.get("codes", []))

    def test_erotic_impact_score(self) -> None:
        from edit_policy import compute_erotic_impact_score

        shots = [
            {
                "id": "f1",
                "heat_phase": "foreplay",
                "duration_sec": 4,
                "dsl": {"action": "undress strips"},
            },
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "coverage_role": "detail",
                "duration_sec": 12,
                "dsl": {
                    "action": "hips-sink thrust",
                    "camera": {"shot_size": "close-up insert"},
                },
            },
            {
                "id": "c1",
                "heat_phase": "climax",
                "wardrobe_state": "bare",
                "duration_sec": 8,
                "dsl": {"action": "arch-finish 高潮 射出"},
            },
        ]
        rep = compute_erotic_impact_score(shots, heat_scale="max")
        self.assertGreaterEqual(rep.get("score", 0), 60)
        self.assertIn(rep.get("grade"), {"A", "S", "B"})

    def test_merged_into_heat_arc(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup", "duration_sec": 6},
            {"id": "a1", "heat_phase": "act", "duration_sec": 12, "dsl": {"action": "hug only"}},
        ]
        rep = lint_heat_arc(shots, heat_scale="max")
        codes = rep.get("codes") or []
        self.assertTrue(
            any(str(c).startswith("SEX_ARC_") for c in codes),
            codes,
        )
        self.assertIn("SEX_DETAIL_CU_MISSING", codes)


class AdultMaxIronStillSource(unittest.TestCase):
    """still_source_strict is wired into validate_film_spec (shipped path)."""

    _DF = {
        "setup": "hook",
        "foreplay": "sensory",
        "act": "action",
        "climax": "action",
        "afterglow": "afterglow",
        "bridge": "bridge",
    }

    def _base_shot(
        self,
        sid: str,
        phase: str,
        wardrobe: str,
        *,
        still_source: str | None = None,
        dur: float | None = None,
    ) -> dict:
        duration = dur if dur is not None else (10.0 if phase in {"act", "climax"} else 4.0)
        sh: dict = {
            "id": sid,
            "heat_phase": phase,
            "dramatic_function": self._DF[phase],
            "wardrobe_state": wardrobe,
            "duration_sec": duration,
            "lipsync": False,
            "nar": "沉腰办穿锁腰高潮顶弄吃进",
            "dsl": {
                "subject": f"{wardrobe} bare skin already undressed clothes discarded",
                "action": "strips hips-sink removes undress arch-finish",
                "motion": "thrust continuous body",
                "story_beat": phase,
                "visible_change": "undress A to B",
                "camera": {"shot_size": "medium full", "angle": "eye level"},
                "wardrobe_state": wardrobe,
            },
        }
        if still_source:
            sh["still_source"] = still_source
        return sh

    def test_write_spec_rejects_full_cast_after_undress(self) -> None:
        from film_spec import FilmSpecError, validate_film_spec

        shots = [
            self._base_shot("s01", "setup", "full"),
            self._base_shot("f01", "foreplay", "partial"),
            self._base_shot("a01", "act", "undressed"),
            self._base_shot("a02", "act", "undressed"),
            self._base_shot("c01", "climax", "bare", still_source="cast_master"),
            self._base_shot("g01", "afterglow", "bare"),
            self._base_shot("b01", "bridge", "bare"),
            self._base_shot("b02", "bridge", "bare"),
        ]
        spec = {
            "title": "still-source-redress",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "spice_level": "extreme",
            "sex_floor_strict": False,
            "sex_vo_strict": False,
            "heat_arc_strict": False,
            "sex_arc_strict": False,
            "sex_wardrobe_strict": True,
            "still_source_strict": True,
            "director_intent": {
                "logline": "成人max peak still 禁全装 cast",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("still source", str(ctx.exception).lower())

    def test_write_spec_allows_undress_anchor(self) -> None:
        from film_spec import validate_film_spec

        shots = [
            self._base_shot("s01", "setup", "full"),
            self._base_shot("f01", "foreplay", "partial"),
            self._base_shot("a01", "act", "undressed", still_source="undress-anchor"),
            self._base_shot("a02", "act", "undressed", still_source="undress-anchor"),
            self._base_shot("a03", "act", "bare", still_source="undress-anchor"),
            self._base_shot("c01", "climax", "bare", still_source="undress-anchor"),
            self._base_shot("g01", "afterglow", "bare", still_source="prior undressed still"),
            self._base_shot("b01", "bridge", "bare"),
        ]
        spec = {
            "title": "still-source-ok",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "spice_level": "extreme",
            "sex_floor_strict": False,
            "sex_vo_strict": False,
            "heat_arc_strict": False,
            "sex_arc_strict": False,
            "sex_wardrobe_strict": True,
            "still_source_strict": True,
            "coitus_strict": False,
            "size_ladder_strict": False,
            "pose_strict": False,
            "montage_strict": False,
            "sex_detail_cu_strict": False,
            "both_undress_strict": False,
            "sex_vo_motion_strict": False,
            "director_intent": {
                "logline": "成人max undress-anchor ok",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        out = validate_film_spec(spec, assign_missing_ids=False)
        self.assertTrue(out)
        pol = spec.get("_still_source_policy") or {}
        self.assertTrue(pol.get("ok"), pol)


class AdultMaxIronDuration(unittest.TestCase):
    def test_below_50_flags(self) -> None:
        shots = [
            {"id": f"s{i}", "heat_phase": "setup", "duration_sec": 6} for i in range(6)
        ]
        shots += [
            {"id": f"a{i}", "heat_phase": "act", "duration_sec": 6} for i in range(2)
        ]
        # 12/48 = 0.25 < 0.50
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        self.assertIn("HEAT_SEX_DURATION_LOW", rep.get("codes", []))
        self.assertAlmostEqual(rep["sex_duration_floor"], 0.50, places=2)

    def test_at_50_ok(self) -> None:
        shots = [
            {"id": f"s{i}", "heat_phase": "setup", "duration_sec": 6} for i in range(4)
        ]
        shots += [
            {"id": f"a{i}", "heat_phase": "act", "duration_sec": 6} for i in range(4)
        ]
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep.get("codes", []))


if __name__ == "__main__":
    unittest.main()
