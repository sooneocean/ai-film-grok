"""heat_scale intimacy ratio + multi-heroine lint (2026-07-21)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    apply_heat_phase_defaults,
    apply_wardrobe_continuity,
    lint_heat_arc,
    lint_multi_heroine,
    lint_sex_vo_spice,
    lint_sex_wardrobe,
    nar_has_sex_verb,
    nar_has_spice,
    resolve_heroine_cast_mode,
    resolve_wardrobe_state,
    wardrobe_undress_rank,
)
from film_spec import validate_film_spec  # noqa: E402


def _spine(phases: list[str], *, wardrobe_ok: bool = True, vo_spice: bool = True) -> list[dict]:
    """Build phase spine. wardrobe_ok + vo_spice fill max sex gates (incl. 2.9.0 impact)."""
    df_map = {
        "setup": "hook",
        "foreplay": "sensory",
        "act": "action",
        "climax": "action",
        "afterglow": "afterglow",
        "bridge": "bridge",
    }
    nar_map = {
        "setup": "展厅落锁。今晚只加演你一场。",
        "foreplay": "肩带一滑，规矩失效。",
        "act": "沉腰吃进。再沉，节奏是她给的。",
        "climax": "她失声。背一弓——这一场办穿了。",
        "afterglow": "贴耳低语：下一场——换你顶。",
        "bridge": "门闩还热，故事未完。",
    }
    shots = []
    undress_assigned = False
    act_i = 0
    detail_assigned = False
    for i, ph in enumerate(phases, 1):
        action = "body moves"
        wardrobe_state = None
        subject = "adult woman"
        coitus_beat = None
        coverage_role = None
        framing = None
        partner_ws = None
        sex_pose = None
        camera = {"shot_size": "medium", "angle": "eye level"}
        if wardrobe_ok:
            if ph == "foreplay" and not undress_assigned:
                action = "removes armor and strips dress off shoulders"
                wardrobe_state = "partial"
                undress_assigned = True
                coitus_beat = "undress"
            elif ph == "act":
                act_i += 1
                partner_ws = "undressed"
                if act_i == 1:
                    action = "straddle-seat hips settle pelvis-lock bare skin skin-to-skin"
                    wardrobe_state = "undressed"
                    subject = "adult woman undressed bare skin"
                    coitus_beat = "union"
                    # size ladder: tighten only (no reopen) medium → CU → insert
                    camera = {
                        "shot_size": "medium",
                        "angle": "slight low",
                        "headroom": "full head with headroom",
                    }
                    sex_pose = "straddle"
                else:
                    action = "hips-sink grind thrust-rhythm bare skin"
                    wardrobe_state = "undressed" if act_i < 3 else "bare"
                    subject = "adult woman undressed bare skin"
                    coitus_beat = "rhythm"
                    sex_pose = "cowgirl" if act_i == 2 else "from_behind"
                    camera = {
                        "shot_size": "close-up",
                        "angle": "slight low",
                        "headroom": "full head with headroom",
                    }
                    if not detail_assigned:
                        coverage_role = "detail"
                        framing = "union_closeup face and pelvis same frame full head headroom"
                        camera = {
                            "shot_size": "close-up insert",
                            "angle": "slight low",
                            "headroom": "full head with headroom",
                        }
                        detail_assigned = True
            elif ph == "climax":
                action = "arch-finish residual tremor bare shoulders 高潮 射出"
                wardrobe_state = "bare"
                subject = "adult woman bare skin after peak"
                coitus_beat = "finish"
                partner_ws = "undressed"
                sex_pose = "missionary_pin"
                camera = {
                    "shot_size": "close-up",
                    "angle": "eye level",
                    "headroom": "full head with headroom",
                }
            elif ph == "setup":
                wardrobe_state = "armored"
                coitus_beat = "entry"
                camera = {
                    "shot_size": "wide",
                    "angle": "eye level",
                    "headroom": "full head with headroom",
                }
            elif ph == "afterglow":
                wardrobe_state = "bare"
                coitus_beat = "hook"
                partner_ws = "undressed"
        dsl = {
            "subject": subject,
            "action": action,
            "motion": "decisive body motion continuous",
            "story_beat": "beat",
            "visible_change": "A to B",
            "focal_character": "kei",
            "camera": camera,
        }
        if wardrobe_state:
            dsl["wardrobe_state"] = wardrobe_state
        if coitus_beat:
            dsl["coitus_beat"] = coitus_beat
        if partner_ws:
            dsl["partner_wardrobe_state"] = partner_ws
        if coverage_role:
            dsl["coverage_role"] = coverage_role
        if framing:
            dsl["framing"] = framing
        if sex_pose:
            dsl["sex_pose"] = sex_pose
        nar = nar_map.get(ph, "短旁白测。") if vo_spice else "灯灭了。故事却刚好开始。"
        shot = {
            "id": f"shot{i:02d}",
            "dramatic_function": df_map.get(ph, "bridge"),
            "heat_phase": ph,
            "nar": nar,
            "lipsync": False,
            "duration_sec": 6,
            "dsl": dsl,
        }
        if wardrobe_state:
            shot["wardrobe_state"] = wardrobe_state
        if coitus_beat:
            shot["coitus_beat"] = coitus_beat
        if partner_ws:
            shot["partner_wardrobe_state"] = partner_ws
        if coverage_role:
            shot["coverage_role"] = coverage_role
        if framing:
            shot["framing"] = framing
        if sex_pose:
            shot["sex_pose"] = sex_pose
        shots.append(shot)
    # Single-act spines still need detail CU somewhere in meat
    if wardrobe_ok and not detail_assigned:
        for sh in shots:
            if sh.get("heat_phase") in {"act", "climax"}:
                sh["coverage_role"] = "detail"
                sh["framing"] = "union_closeup"
                sh["dsl"]["coverage_role"] = "detail"
                sh["dsl"]["framing"] = "union_closeup"
                sh["dsl"]["camera"] = {
                    "shot_size": "close-up insert",
                    "angle": "slight low",
                }
                break
    return shots


@pytest.mark.slow
class HeatArcLintTests(unittest.TestCase):
    @pytest.mark.slow
    def test_max_extreme_empty_act_climax_warns(self) -> None:
        # all setup — extreme for max → soft warning only
        shots = _spine(["setup"] * 8, wardrobe_ok=False)
        rep = lint_heat_arc(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ACT_CLIMAX_EMPTY", rep["codes"])
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertEqual(rep["sex_duration_ratio"], 0.0)

    @pytest.mark.slow
    def test_max_mid_ratio_no_forced_warning(self) -> None:
        # 4/8 act+climax by duration = 50% ≥ 50% IRON floor.
        shots = _spine(["setup", "foreplay", "act", "act", "act", "climax", "afterglow", "bridge"])
        rep = lint_heat_arc(shots, heat_scale="max", advise=False)
        self.assertTrue(rep["ok"], rep)
        self.assertNotIn("HEAT_ADVISORY_INTIMACY", rep["codes"])
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.50, places=3)

    @pytest.mark.slow
    def test_max_sex_duration_below_50_warns(self) -> None:
        # only 1×6s act of 8×6s = 12.5% < 50%
        shots = _spine(
            ["setup", "setup", "setup", "foreplay", "foreplay", "act", "afterglow", "bridge"]
        )
        rep = lint_heat_arc(shots, heat_scale="max", advise=False)
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.125, places=3)
        self.assertEqual(rep["sex_duration_floor"], 0.50)

    @pytest.mark.slow
    def test_act_full_armor_wardrobe_fails(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"],
            wardrobe_ok=False,
        )
        # force armored act without undress language
        for sh in shots:
            if sh["heat_phase"] in {"act", "climax"}:
                sh["wardrobe_state"] = "armored"
                sh["dsl"]["wardrobe_state"] = "armored"
                sh["dsl"]["action"] = "straddle fully armored intact outfit"
                sh["dsl"]["subject"] = "adult woman full armor intact"
        rep = lint_heat_arc(shots, heat_scale="max")
        self.assertIn("HEAT_SEX_WARDROBE_DRESSED", rep["codes"])
        self.assertIn("HEAT_UNDRESS_BEAT_MISSING", rep["codes"])

    @pytest.mark.slow
    def test_undress_ladder_passes(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"]
        )
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertTrue(rep["ok"], rep)
        self.assertGreaterEqual(len(rep["undress_beats"]), 1)

    @pytest.mark.slow
    def test_wardrobe_re_dress_fails(self) -> None:
        """衣服回穿：undressed 之后又 full → HEAT_WARDROBE_RE_DRESS."""
        shots = _spine(
            ["setup", "foreplay", "act", "climax", "afterglow", "bridge", "bridge", "bridge"]
        )
        for sh in shots:
            if sh["heat_phase"] == "afterglow":
                sh["wardrobe_state"] = "full"
                sh["dsl"]["wardrobe_state"] = "full"
                sh["dsl"]["action"] = "stands fully clothed neat dress"
                sh["dsl"]["subject"] = "adult woman full dress intact"
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertIn("HEAT_WARDROBE_RE_DRESS", rep["codes"])
        self.assertFalse(rep["ok"])

    @pytest.mark.slow
    def test_wardrobe_re_dress_clamped_on_max(self) -> None:
        """max: 回穿被 clamp 到 peak，后镜保持 undressed/bare."""
        shots = _spine(
            ["setup", "foreplay", "act", "climax", "afterglow", "bridge", "bridge", "bridge"]
        )
        # peak should be bare/undressed from spine; force afterglow full then clamp
        for sh in shots:
            if sh["heat_phase"] == "afterglow":
                sh["wardrobe_state"] = "full"
                sh["dsl"]["wardrobe_state"] = "full"
                sh["dsl"]["subject"] = "adult woman full dress intact neat dress"
                sh["dsl"]["action"] = "stands fully clothed"
        cont = apply_wardrobe_continuity(shots, heat_scale="max")
        # clamp re-dress OR phase escalate may both raise afterglow off full
        self.assertTrue(cont.get("clamped_ids") or cont.get("escalated"), cont)
        for sh in shots:
            if sh["heat_phase"] == "afterglow":
                rank = wardrobe_undress_rank(sh["wardrobe_state"])
                self.assertIsNotNone(rank)
                self.assertGreaterEqual(rank, wardrobe_undress_rank("undressed") or 0)
                # start_pose must acknowledge already undressed
                sp = str(sh["dsl"].get("start_pose") or "").lower()
                self.assertTrue(
                    any(k in sp for k in ("already", "prior", "bare", "undress", "half")),
                    sp,
                )

    @pytest.mark.slow
    def test_wardrobe_text_conflict_detected(self) -> None:
        shots = [
            {
                "id": "shot01",
                "heat_phase": "act",
                "dramatic_function": "action",
                "nar": "沉腰办穿。",
                "wardrobe_state": "bare",
                "dsl": {
                    "subject": "adult woman full wardrobe full dress intact neat dress",
                    "action": "hips sink",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "c",
                    "wardrobe_state": "bare",
                },
            }
        ]
        rep = lint_sex_wardrobe(shots, heat_scale="max")
        self.assertIn("HEAT_WARDROBE_TEXT_CONFLICT", rep["codes"])

    @pytest.mark.slow
    def test_wardrobe_continuity_inherits_forward(self) -> None:
        shots = [
            {
                "id": "shot01",
                "heat_phase": "foreplay",
                "dramatic_function": "sensory",
                "nar": "肩带一滑，卸甲。",
                "wardrobe_state": "partial",
                "dsl": {
                    "subject": "x",
                    "action": "removes armor strips",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "armor falls",
                    "wardrobe_state": "partial",
                },
            },
            {
                "id": "shot02",
                "heat_phase": "act",
                "dramatic_function": "action",
                "nar": "沉腰吃进。",
                # no wardrobe_state — must inherit partial (or bump undressed via max default)
                "dsl": {
                    "subject": "x",
                    "action": "hips sink",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "c",
                },
            },
        ]
        cont = apply_wardrobe_continuity(shots, heat_scale="max")
        # inherit partial then IRON phase floor raises act → undressed
        self.assertTrue(
            "shot02" in cont["filled_ids"]
            or any(e.get("id") == "shot02" for e in (cont.get("escalated") or []))
        )
        self.assertEqual(shots[1]["wardrobe_state"], "undressed")
        self.assertEqual(shots[1]["dsl"]["wardrobe_state"], "undressed")
        self.assertGreaterEqual(
            wardrobe_undress_rank(shots[1]["wardrobe_state"]) or 0,
            wardrobe_undress_rank("undressed") or 0,
        )

    @pytest.mark.slow
    def test_write_spec_clamps_re_dress(self) -> None:
        """Product: re-dress is clamped (must trigger), not only hard-failed."""
        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"]
        )
        for sh in shots:
            sh["dsl"]["camera"] = {"shot_size": "medium full", "angle": "eye level"}
            sh["lipsync"] = False
            if sh["heat_phase"] == "afterglow":
                sh["wardrobe_state"] = "armored"
                sh["dsl"]["wardrobe_state"] = "armored"
                sh["dsl"]["action"] = "stands fully armored intact outfit"
                sh["dsl"]["subject"] = "adult woman full armor intact"
        spec = {
            "title": "测回穿自动钳制",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "sex_wardrobe_strict": True,
            "sex_floor_strict": False,
            "sex_vo_strict": False,
            "heat_arc_strict": False,
            "coitus_strict": False,
            "size_ladder_strict": False,
            "pose_strict": False,
            "montage_strict": False,
            "sex_detail_cu_strict": False,
            "both_undress_strict": False,
            "sex_arc_strict": False,
            "sex_vo_motion_strict": False,
            "framing_strict": False,
            "composition_strict": False,
            "director_intent": {
                "logline": "成人max卸装后回穿应被 clamp 到 peak",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        # validate mutates spec in place; returns shot list
        validate_film_spec(spec, assign_missing_ids=False)
        cont = spec.get("_wardrobe_continuity") or {}
        self.assertTrue(cont.get("clamped_ids"), cont)
        # afterglow no longer armored
        for sc in spec.get("scenes") or []:
            for sh in sc.get("shots") or []:
                if sh.get("heat_phase") == "afterglow":
                    self.assertNotEqual(sh.get("wardrobe_state"), "armored")
                    self.assertGreaterEqual(
                        wardrobe_undress_rank(sh.get("wardrobe_state")) or 0,
                        wardrobe_undress_rank("undressed") or 0,
                    )
        # residual re-dress codes should be cleared by clamp
        heat = spec.get("_heat_arc") or {}
        self.assertNotIn("HEAT_WARDROBE_RE_DRESS", heat.get("codes") or [])

    @pytest.mark.slow
    def test_resolve_wardrobe_from_markers(self) -> None:
        shot = {
            "id": "shot05",
            "heat_phase": "act",
            "dsl": {
                "subject": "heroine",
                "action": "hips sink",
                "motion": "m",
                "story_beat": "b",
                "visible_change": "armor off bare skin",
            },
        }
        self.assertIn(resolve_wardrobe_state(shot), {"partial", "undressed", "bare"})

    @pytest.mark.slow
    def test_sex_duration_weighted_not_shot_count(self) -> None:
        # 1 long act (18s) + 3×6s non-sex = 18/36 = 50% sex even if shot-count is 1/4
        shots = [
            {
                "id": "shot01",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "落锁。今晚只加演你。",
                "wardrobe_state": "armored",
                "dsl": {
                    "subject": "x",
                    "action": "stands",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "c",
                    "wardrobe_state": "armored",
                },
            },
            {
                "id": "shot02",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "铠甲卸下，肩带失序。",
                "dsl": {
                    "subject": "x",
                    "action": "removes armor strips dress",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "armor falls",
                },
            },
            {
                "id": "shot03",
                "heat_phase": "setup",
                "dramatic_function": "hook",
                "duration_sec": 6,
                "nar": "规矩失效，贴身半掌。",
                "dsl": {
                    "subject": "x",
                    "action": "a",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "c",
                },
            },
            {
                "id": "shot04",
                "heat_phase": "act",
                "dramatic_function": "action",
                "duration_sec": 18,
                "nar": "沉腰吃进，再磨一遍。",
                "wardrobe_state": "bare",
                "dsl": {
                    "subject": "x bare exposed skin",
                    "action": "hips sink bare",
                    "motion": "m",
                    "story_beat": "b",
                    "visible_change": "c",
                    "wardrobe_state": "bare",
                },
            },
        ]
        # mark shot02 as foreplay so undress beat counts
        shots[1]["heat_phase"] = "foreplay"
        shots[1]["dramatic_function"] = "sensory"
        rep = lint_heat_arc(shots, heat_scale="max")
        self.assertAlmostEqual(rep["sex_duration_ratio"], 0.5, places=2)
        self.assertAlmostEqual(rep["sex_shot_ratio"], 0.25, places=2)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertNotIn("HEAT_SEX_WARDROBE_DRESSED", rep["codes"])

    @pytest.mark.slow
    def test_hardcore_profile_raises_sex_floor(self) -> None:
        # 25% sex fails hardcore 55% floor
        shots = _spine(
            ["setup", "setup", "setup", "foreplay", "act", "climax", "afterglow", "bridge"]
        )
        rep = lint_heat_arc(shots, heat_scale="max", audience_profile="hardcore_male", advise=False)
        self.assertIn("HEAT_SEX_DURATION_LOW", rep["codes"])
        self.assertEqual(rep["sex_duration_floor"], 0.55)

    @pytest.mark.slow
    def test_advise_adds_info_not_hard(self) -> None:
        shots = _spine(["setup"] * 5 + ["act", "climax", "afterglow"])
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        # may have info advisories; extreme floor may or may not warn
        self.assertTrue(any(i.get("severity") == "info" for i in rep["issues"]) or rep["ok"])

    @pytest.mark.slow
    def test_no_heat_scale_no_ratio_gate(self) -> None:
        shots = _spine(["setup"] * 8)
        rep = lint_heat_arc(shots, heat_scale=None)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["warning_count"], 0)

    @pytest.mark.slow
    def test_apply_heat_phase_defaults_no_climax_guess(self) -> None:
        shots = [
            {"id": "shot01", "dramatic_function": "hook", "nar": "x"},
            {"id": "shot02", "dramatic_function": "action", "nar": "y"},
        ]
        filled = apply_heat_phase_defaults(shots)
        self.assertEqual(len(filled), 2)
        self.assertEqual(shots[0]["heat_phase"], "setup")
        self.assertEqual(shots[1]["heat_phase"], "act")  # no auto climax


@pytest.mark.slow
class MultiHeroineLintTests(unittest.TestCase):
    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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


@pytest.mark.slow
class ResolveCastModeTests(unittest.TestCase):
    @pytest.mark.slow
    def test_default_single(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="雨夜女司机色气短片",
            cast_ids=["hero", "partner"],
            cast_masters={"hero": "cast/hero-v1.png"},
        )
        self.assertEqual(r["mode"], "single")
        self.assertFalse(r["active"])

    @pytest.mark.slow
    def test_prompt_multi_with_two_masters(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="双女主 百合 两位女主办事完成",
            cast_masters={"kei": "a.png", "viv": "b.png"},
        )
        self.assertEqual(r["mode"], "multi")
        self.assertTrue(r["active"])
        self.assertGreaterEqual(len(r["heroine_ids"]), 2)

    @pytest.mark.slow
    def test_explicit_single_wins(self) -> None:
        r = resolve_heroine_cast_mode(
            cast_mode="single",
            prompt_blob="双女主",
            cast_masters={"a": "1.png", "b": "2.png"},
        )
        self.assertEqual(r["mode"], "single")

    @pytest.mark.slow
    def test_two_ref_images_plus_prompt(self) -> None:
        r = resolve_heroine_cast_mode(
            prompt_blob="两个女人一起",
            female_ref_image_count=2,
            cast_masters={"h1": "x.png", "h2": "y.png"},
        )
        self.assertEqual(r["mode"], "multi")


@pytest.mark.slow
class ValidateFilmSpecHeatTests(unittest.TestCase):
    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_write_spec_max_sex_floor_hard_fail(self) -> None:
        # 8 setup only — max defaults sex_floor_strict → hard fail
        shots = _spine(["setup"] * 8, wardrobe_ok=False)
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
        msg = str(ctx.exception).upper()
        self.assertTrue(
            "SEX_DURATION" in msg or "HEAT ARC" in msg or "ACT_CLIMAX" in msg or "SETUP" in msg,
            msg,
        )

    @pytest.mark.slow
    def test_write_spec_max_sex_floor_pass_with_enough_act(self) -> None:
        # 6/8 intimacy (foreplay+act×4+climax), 5/8 sex duration ≥50%
        shots = _spine(["setup", "foreplay", "act", "act", "act", "act", "climax", "afterglow"])
        for sh in shots:
            sh["lipsync"] = False
            # keep _spine size ladder (tighten only); do not reopen mid-act
            cam = sh.get("dsl", {}).get("camera") or {}
            if not cam.get("shot_size"):
                sh["dsl"]["camera"] = {
                    "shot_size": "medium",
                    "angle": "eye level",
                    "headroom": "full head with headroom",
                }
        # craft for montage_strict; size_ladder can soft-fail via false for this floor test
        spec = {
            "title": "测性爱时长过关",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "edit_craft": ["insert", "smash_cut", "match_cut", "montage"],
            "size_ladder_strict": False,
            "framing_strict": False,
            "composition_strict": False,
            "director_intent": {
                "logline": "成人max性爱够秒",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertGreaterEqual(spec["_heat_arc"]["sex_duration_ratio"], 0.50)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", spec["_heat_arc"]["codes"])
        self.assertNotIn("HEAT_SEX_WARDROBE_DRESSED", spec["_heat_arc"]["codes"])

    @pytest.mark.slow
    def test_vo_spice_markers(self) -> None:
        self.assertTrue(nar_has_spice("沉腰吃进。"))
        self.assertTrue(nar_has_sex_verb("这一场办穿了。"))
        self.assertFalse(nar_has_spice("灯灭了。故事却刚好开始。"))

    @pytest.mark.slow
    def test_literary_vo_fails_max(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"],
            vo_spice=False,
        )
        rep = lint_sex_vo_spice(shots, heat_scale="max")
        self.assertIn("HEAT_VO_SPICE_MISSING", rep["codes"])
        self.assertIn("HEAT_VO_SEX_VERB_WEAK", rep["codes"])

    @pytest.mark.slow
    def test_spicy_vo_passes(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"]
        )
        rep = lint_sex_vo_spice(shots, heat_scale="max")
        self.assertTrue(rep["ok"], rep)
        self.assertGreaterEqual(rep["spice_ratio"], 0.85)

    @pytest.mark.slow
    def test_write_spec_bland_vo_hard_fail(self) -> None:
        shots = _spine(
            ["setup", "foreplay", "act", "act", "act", "act", "climax", "afterglow"],
            vo_spice=False,
        )
        for sh in shots:
            sh["dsl"]["camera"] = {"shot_size": "medium full", "angle": "eye level"}
            sh["lipsync"] = False
        spec = {
            "title": "测文艺旁白硬闸",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "heat_arc_strict": False,
            "sex_floor_strict": False,
            # disable auto-apply so VO strict remains a hard fail surface
            "sex_vo_auto_apply": False,
            "director_intent": {
                "logline": "成人max但旁白文艺",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        with self.assertRaises(Exception) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        msg = str(ctx.exception).upper()
        self.assertTrue("VO" in msg or "SPICE" in msg, msg)

    def test_write_spec_vo_auto_apply_fixes_bland(self) -> None:
        """Default max: bland nar is auto-reinforced before VO hard-fail."""
        from edit_policy import apply_vo_spice_auto, nar_has_spice

        shots = _spine(
            ["setup", "foreplay", "act", "act", "climax", "afterglow", "bridge", "bridge"],
            vo_spice=False,
        )
        for sh in shots:
            sh["nar"] = "灯暗了下来。"
            sh["dsl"]["camera"] = {"shot_size": "close-up", "angle": "eye level"}
            if sh["heat_phase"] == "act":
                sh["dsl"]["camera"] = {"shot_size": "close-up insert", "angle": "low"}
                sh["coverage_role"] = "detail"
            sh["lipsync"] = False
        fixed = apply_vo_spice_auto(shots, spice_level="extreme")
        self.assertGreater(fixed["fixed"], 0)
        self.assertTrue(any(nar_has_spice(sh.get("nar")) for sh in shots if sh.get("nar")))

    @pytest.mark.slow
    def test_write_spec_armored_act_auto_escalates(self) -> None:
        """IRON: armored act is auto-raised to undressed|bare (能脱就脱), not left dressed."""
        shots = _spine(
            ["setup", "foreplay", "act", "act", "act", "act", "climax", "afterglow"],
            wardrobe_ok=False,
        )
        for sh in shots:
            sh["dsl"]["camera"] = {"shot_size": "medium full", "angle": "eye level"}
            sh["lipsync"] = False
            if sh["heat_phase"] in {"act", "climax"}:
                sh["wardrobe_state"] = "armored"
                sh["dsl"]["wardrobe_state"] = "armored"
                sh["dsl"]["action"] = "straddle in full armor"
        spec = {
            "title": "测铠甲办事自动卸装",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "heat_arc_strict": False,
            "sex_floor_strict": False,
            "sex_vo_strict": False,
            "coitus_strict": False,
            "size_ladder_strict": False,
            "pose_strict": False,
            "montage_strict": False,
            "sex_detail_cu_strict": False,
            "both_undress_strict": False,
            "sex_arc_strict": False,
            "sex_vo_motion_strict": False,
            "adult_max_director": {"strict": False},
            "director_intent": {
                "logline": "成人max全装办事应被自动卸装",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        for sh in shots:
            if sh["heat_phase"] == "act":
                self.assertIn(sh.get("wardrobe_state"), {"undressed", "bare"}, sh)
            if sh["heat_phase"] == "climax":
                self.assertEqual(sh.get("wardrobe_state"), "bare", sh)
        cont = spec.get("_wardrobe_continuity") or {}
        self.assertTrue(cont.get("escalated") or cont.get("filled_ids"), cont)


if __name__ == "__main__":
    unittest.main()
