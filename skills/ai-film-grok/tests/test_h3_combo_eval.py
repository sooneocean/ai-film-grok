"""Unit tests for H3 combo matrix + pure scorer/verdict (no Comfy)."""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from h3_combo_eval import (
    DEFAULT_SEED, DEFAULT_STEPS, build_combo_matrix, build_eval_film_spec,
    load_combo_winners, merge_winners_into_effect_defaults, prepare_eval_root,
    rank_lanes, score_combo_row, winner_tips_from_registry, write_winners_registry,
)
from h3_mode import effect_tips, preferred_mode_for_lane

class ComboMatrixTests(unittest.TestCase):
    def test_matrix_covers_t2v_i2v_r2v(self) -> None:
        combos = build_combo_matrix(include_flf=True)
        modes = {c.mode for c in combos}
        self.assertIn("t2v", modes); self.assertIn("i2v", modes); self.assertIn("r2v", modes)
        families = {c.family for c in combos}
        for f in ("high_motion", "dialogue_mandarin", "soft_portrait", "env_no_face"):
            self.assertIn(f, families)
        for c in combos:
            self.assertEqual(c.seed, DEFAULT_SEED); self.assertEqual(c.steps, DEFAULT_STEPS)
    def test_flf_can_be_excluded(self) -> None:
        self.assertFalse(any(c.mode == "flf" for c in build_combo_matrix(include_flf=False)))
    def test_film_spec_has_unique_shots(self) -> None:
        ids = [s["id"] for s in build_eval_film_spec()["scenes"][0]["shots"]]
        self.assertEqual(len(ids), len(set(ids)))

class ScorerTests(unittest.TestCase):
    def test_identity_score_prefers_low_l1(self) -> None:
        good = score_combo_row({"motion_mean_absdiff": 5.0, "identity": {"start_l1": 9.0, "mid_l1": 12.0, "end_l1": 15.0}})
        bad = score_combo_row({"motion_mean_absdiff": 5.0, "identity": {"start_l1": 90.0, "mid_l1": 90.0, "end_l1": 90.0}})
        self.assertGreater(good["identity_score"], bad["identity_score"])
    def test_rank_lanes_names_winners_with_numeric_scores(self) -> None:
        rows = [
            {"ok": True, "combo_id": "soft_i2v", "mode": "i2v", "family": "soft_portrait", "lane_tags": ["hero_identity_lock"], "motion_mean_absdiff": 4.3, "identity": {"start_l1": 9.1, "mid_l1": 13.0, "end_l1": 21.0}, "mouth_region_std_change": 0.5},
            {"ok": True, "combo_id": "soft_r2v", "mode": "r2v", "family": "soft_portrait", "lane_tags": ["hero_identity_lock"], "motion_mean_absdiff": 6.5, "identity": {"start_l1": 31.0, "mid_l1": 34.0, "end_l1": 40.0}},
            {"ok": True, "combo_id": "high_i2v", "mode": "i2v", "family": "high_motion", "lane_tags": ["high_motion_energy"], "motion_mean_absdiff": 23.3, "identity": {"start_l1": 9.2, "mid_l1": 30.0, "end_l1": 57.0}},
            {"ok": True, "combo_id": "high_r2v", "mode": "r2v", "family": "high_motion", "lane_tags": ["high_motion_energy"], "motion_mean_absdiff": 33.9, "identity": {"start_l1": 11.9, "mid_l1": 58.0, "end_l1": 25.0}},
            {"ok": True, "combo_id": "dlg_i2v", "mode": "i2v", "family": "dialogue_mandarin", "lane_tags": ["dialogue_mouth_energy"], "motion_mean_absdiff": 2.6, "identity": {"start_l1": 9.2, "mid_l1": 13.5, "end_l1": 13.8}, "mouth_region_std_change": 0.8},
            {"ok": True, "combo_id": "dlg_r2v", "mode": "r2v", "family": "dialogue_mandarin", "lane_tags": ["dialogue_mouth_energy"], "motion_mean_absdiff": 13.7, "identity": {"start_l1": 54.5, "mid_l1": 55.0, "end_l1": 55.0}, "mouth_region_std_change": 1.9},
            {"ok": True, "combo_id": "env_t2v", "mode": "t2v", "family": "env_no_face", "lane_tags": ["faceless_env"], "motion_mean_absdiff": 19.3, "identity": {"start_l1": None}},
        ]
        w = rank_lanes(rows)["winners"]
        self.assertEqual(w["hero_identity_lock"]["combo_id"], "soft_i2v")
        self.assertEqual(w["high_motion_energy"]["combo_id"], "high_r2v")
        self.assertEqual(w["dialogue_mouth_energy"]["combo_id"], "dlg_i2v")
        self.assertEqual(w["faceless_env"]["combo_id"], "env_t2v")
    def test_merge_winners_defaults(self) -> None:
        verdict = rank_lanes([
            {"ok": True, "combo_id": "soft_i2v", "mode": "i2v", "family": "soft_portrait", "lane_tags": ["hero_identity_lock"], "motion_mean_absdiff": 4.0, "identity": {"start_l1": 8.0, "mid_l1": 10.0, "end_l1": 12.0}},
            {"ok": True, "combo_id": "high_r2v", "mode": "r2v", "family": "high_motion", "lane_tags": ["high_motion_energy"], "motion_mean_absdiff": 34.0, "identity": {"start_l1": 12.0, "mid_l1": 20.0, "end_l1": 25.0}},
            {"ok": True, "combo_id": "dlg_i2v", "mode": "i2v", "family": "dialogue_mandarin", "lane_tags": ["dialogue_mouth_energy"], "motion_mean_absdiff": 3.0, "identity": {"start_l1": 9.0, "mid_l1": 11.0, "end_l1": 12.0}, "mouth_region_std_change": 1.0},
            {"ok": True, "combo_id": "env_t2v", "mode": "t2v", "family": "env_no_face", "lane_tags": ["faceless_env"], "motion_mean_absdiff": 18.0, "identity": {"start_l1": None}},
        ])
        doc = merge_winners_into_effect_defaults(verdict)
        self.assertEqual(doc["lanes"]["hero_identity_lock"]["preferred_mode"], "i2v")
        self.assertEqual(doc["lanes"]["high_motion_energy"]["preferred_mode"], "r2v")

class RegistryMergeTests(unittest.TestCase):
    def test_write_load_and_effect_tips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "w.json"
            doc = {"schema_version": 1, "kind": "h3-combo-winners", "lanes": {
                "hero_identity_lock": {"preferred_mode": "i2v", "prompt_family": "soft_portrait", "winner": {"score": 88.0}},
                "high_motion_energy": {"preferred_mode": "r2v", "prompt_family": "high_motion", "winner": {"score": 33.9}},
                "dialogue_mouth_energy": {"preferred_mode": "i2v", "prompt_family": "dialogue_mandarin", "winner": {"score": 5.0}},
                "faceless_env": {"preferred_mode": "t2v", "prompt_family": "env_no_face", "winner": {"score": 19.0}},
            }, "weapon_defaults": {"steps": 20, "duration_sec": 5.0}}
            write_winners_registry(doc, path=path)
            tips = winner_tips_from_registry(load_combo_winners(path))
            self.assertTrue(any("身份锁脸" in t for t in tips))
            et = effect_tips("i2v")
            self.assertTrue(any("combo" in t for t in et))
    def test_prepare_eval_root_writes_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "eval"
            prepare_eval_root(root)
            matrix = json.loads((root / "compare" / "combo-matrix.json").read_text())
            self.assertEqual(matrix["kind"], "h3-combo-matrix")

class PreferredModeTests(unittest.TestCase):
    def test_preferred_mode_type(self) -> None:
        mode = preferred_mode_for_lane("hero_identity_lock")
        self.assertTrue(mode is None or isinstance(mode, str))


class FamilyApplyTests(unittest.TestCase):
    def test_fill_empty_dsl_from_family(self) -> None:
        from h3_combo_eval import apply_combo_family_to_shot

        thin = {"id": "s1", "shot_role": "hero", "dsl": {}}
        out = apply_combo_family_to_shot(thin, "soft_portrait_alive")
        self.assertEqual(out.get("_combo_prompt_family_applied"), "soft_portrait_alive")
        dsl = out.get("dsl") or {}
        self.assertTrue(str(dsl.get("action") or "").strip())
        self.assertIn("eyes", str(dsl.get("action") or "").lower())

    def test_does_not_overwrite_author_action(self) -> None:
        from h3_combo_eval import apply_combo_family_to_shot

        author = {
            "id": "s1",
            "dsl": {"action": "CUSTOM_AUTHOR_ACTION_ONLY"},
        }
        out = apply_combo_family_to_shot(author, "high_motion_max")
        self.assertEqual(out["dsl"]["action"], "CUSTOM_AUTHOR_ACTION_ONLY")
        # other empty keys still fill
        self.assertTrue(str(out["dsl"].get("motion") or "").strip())

    def test_force_overwrites(self) -> None:
        from h3_combo_eval import apply_combo_family_to_shot

        author = {"id": "s1", "dsl": {"action": "KEEP_ME"}}
        out = apply_combo_family_to_shot(author, "high_motion_max", force=True)
        self.assertNotEqual(out["dsl"]["action"], "KEEP_ME")

    def test_production_prompt_gets_family_micro_life(self) -> None:
        """Empty-DSL hero shot should pick soft_portrait_alive and inject micro-life."""
        from pathlib import Path
        from h3_workflow import _prompt_for_shot

        thin = {
            "id": "s_soft_prod",
            "shot_role": "hero",
            "heat_phase": "setup",
            "dramatic_function": "reaction",
            "duration_sec": 5,
            "dsl": {},
        }
        film = {"_i2v_profile": "h3_primary", "i2v_profile": "h3_primary"}
        prompt = _prompt_for_shot(Path("/tmp"), thin, mode="i2v", spec=film)
        low = prompt.lower()
        self.assertTrue(
            "eyes" in low or "breath" in low or "micro" in low,
            msg=f"expected micro-life from soft_portrait_alive, got: {prompt[:400]}",
        )
        self.assertNotIn("HIGH MOTION priority: large visible pose/body change across the timeline", prompt)

    def test_high_motion_family_header(self) -> None:
        from pathlib import Path
        from h3_workflow import _prompt_for_shot

        shot = {
            "id": "s_hi_prod",
            "shot_role": "hero",
            "heat_phase": "act",
            "dramatic_function": "action",
            "duration_sec": 5,
            "prompt_tier": "high",
            "dsl": {"prompt_tier": "high"},
        }
        film = {"_i2v_profile": "h3_primary"}
        prompt = _prompt_for_shot(Path("/tmp"), shot, mode="r2v", spec=film)
        self.assertIn("HIGH MOTION", prompt.upper())

    def test_winners_dialogue_family_aligned(self) -> None:
        from h3_combo_eval import load_combo_winners

        data = load_combo_winners() or {}
        lane = (data.get("lanes") or {}).get("dialogue_mouth_energy") or {}
        # R5 mouth-metric winner may be dialogue_mouth_flat; policy requires
        # prompt_family == winner.family (no stale mismatch).
        self.assertIn(
            lane.get("prompt_family"),
            {"dialogue_mouth_max", "dialogue_mouth_flat", "dialogue_mandarin"},
        )
        winner = lane.get("winner") or {}
        if winner.get("family"):
            self.assertEqual(winner.get("family"), lane.get("prompt_family"))


if __name__ == "__main__":
    unittest.main()


class Round2MatrixTests(unittest.TestCase):
    def test_r2_matrix_covers_optimized_families(self) -> None:
        from h3_combo_eval import build_combo_matrix, PROMPT_FAMILIES
        combos = build_combo_matrix(round=2, include_flf=False)
        modes = {c.mode for c in combos}
        self.assertIn("i2v", modes)
        self.assertIn("r2v", modes)
        self.assertIn("t2v", modes)
        fams = {c.family for c in combos}
        for f in ("soft_portrait_alive", "high_motion_max", "dialogue_mouth_max", "env_kinetic"):
            self.assertIn(f, fams)
            self.assertIn(f, PROMPT_FAMILIES)

    def test_r3_timeline_ab_pairs(self) -> None:
        from h3_combo_eval import (
            build_combo_matrix,
            compile_family_author_prompt,
            prepare_eval_root,
            PROMPT_FAMILIES,
        )
        combos = build_combo_matrix(round=3, include_flf=False)
        fams = {c.family for c in combos}
        self.assertIn("high_motion_flat", fams)
        self.assertIn("high_motion_max", fams)
        self.assertIn("dialogue_mouth_flat", fams)
        self.assertIn("dialogue_mouth_max", fams)
        tl = compile_family_author_prompt("high_motion_max", duration_sec=5)
        flat = compile_family_author_prompt("high_motion_flat", duration_sec=5)
        self.assertIn("[0s-", tl)
        self.assertNotIn("[0s-", flat)
        self.assertIn("Primary action", tl)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ab"
            prepare_eval_root(root, combos=combos)
            p_tl = (root / "receipts" / "prompts" / "s_ab_hi_tl.i2v.txt").read_text()
            p_flat = (root / "receipts" / "prompts" / "s_ab_hi_flat.i2v.txt").read_text()
            self.assertIn("[0s-", p_tl)
            self.assertNotIn("[0s-", p_flat)
            for f in ("high_motion_flat", "dialogue_mouth_flat"):
                self.assertIn(f, PROMPT_FAMILIES)

    def test_r4_post_fix_matrix(self) -> None:
        from h3_combo_eval import build_combo_matrix, compile_family_author_prompt

        combos = build_combo_matrix(round=4, include_flf=False)
        ids = {c.combo_id for c in combos}
        self.assertIn("r4_high_tl_r2v", ids)
        self.assertIn("r4_dlg_tl_i2v", ids)
        self.assertIn("r4_high_flat_r2v", ids)
        dlg = compile_family_author_prompt("dialogue_mouth_max", duration_sec=5)
        self.assertIn("[0s-", dlg)
        self.assertIn("MOUTH ENERGY", dlg)
        self.assertNotIn("HIGH MOTION", dlg)

    def test_rank_lanes_best_of_merges_rounds(self) -> None:
        from h3_combo_eval import rank_lanes_best_of
        r1 = [{"ok": True, "combo_id": "soft_i2v", "mode": "i2v", "family": "soft_portrait",
               "lane_tags": ["hero_identity_lock"], "motion_mean_absdiff": 2.0,
               "identity": {"start_l1": 8.0, "mid_l1": 12.0, "end_l1": 15.0}}]
        r2 = [{"ok": True, "combo_id": "r2_soft_alive_i2v", "mode": "i2v", "family": "soft_portrait_alive",
               "lane_tags": ["hero_identity_lock"], "motion_mean_absdiff": 5.0,
               "identity": {"start_l1": 8.5, "mid_l1": 11.0, "end_l1": 14.0}}]
        v = rank_lanes_best_of(r1, r2)
        self.assertIn("hero_identity_lock", v["lanes_complete"])
        self.assertEqual(v["rounds_merged"], 2)
