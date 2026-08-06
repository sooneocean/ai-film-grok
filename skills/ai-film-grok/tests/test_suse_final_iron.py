"""2026-08-06 suse EP01 official final IRON — A1/A2/A3 contracts."""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from final.voice import check_vo_window_triangle  # noqa: E402

_DF = {
    "setup": "hook",
    "foreplay": "sensory",
    "act": "action",
    "climax": "action",
    "afterglow": "afterglow",
    "bridge": "bridge",
}
_MOTION = {
    "setup": "unlatch door enter arrive reveal, threshold walk turn, initial read",
    "foreplay": "touch skin breath tremble shiver heat rise sweat drip pulse trace",
    "act": "push press grip lock thrust plant deep unhook slam strike lean grab",
    "climax": "thrust spasm slam lock press exhale burst settle peak drop lift",
    "afterglow": "hold settle exhale soften linger residual blink still slow",
    "bridge": "pan track transition follow dolly cross pass connector corridor",
}


def _shot(sid: str, phase: str, wardrobe: str, *, dur: float) -> dict:
    return {
        "id": sid,
        "heat_phase": phase,
        "dramatic_function": _DF[phase],
        "wardrobe_state": wardrobe,
        "duration_sec": dur,
        "lipsync": False,
        "emotion": phase,
        "nar": "沉腰办穿锁腰高潮顶弄吃进",
        "dsl": {
            "subject": f"{wardrobe} bare skin already undressed clothes discarded",
            "action": _MOTION[phase],
            "motion": _MOTION[phase],
            "story_beat": phase,
            "visible_change": "undress A to B",
            "camera": {"shot_size": "medium full", "angle": "eye level"},
            "wardrobe_state": wardrobe,
        },
        "still_source": "undress-anchor" if phase in {"act", "climax", "afterglow"} else None,
    }


class SexFloorNoSilentPadTests(unittest.TestCase):
    """A1: HEAT_SEX_DURATION_LOW must not silently max(act, 10)."""

    def test_short_h3_act_slots_not_padded_to_ten(self) -> None:
        # ~20% sex share with short H3-like 5.2s plates — floor fails, no 10s invent.
        shots = [
            _shot("s01", "setup", "full", dur=5.2),
            _shot("s02", "setup", "full", dur=5.2),
            _shot("s03", "setup", "partial", dur=5.2),
            _shot("s04", "setup", "partial", dur=5.2),
            _shot("f01", "foreplay", "partial", dur=5.2),
            _shot("a01", "act", "undressed", dur=5.2),
            _shot("c01", "climax", "bare", dur=5.2),
            _shot("g01", "afterglow", "bare", dur=5.2),
        ]
        for sh in shots:
            if sh.get("still_source") is None:
                sh.pop("still_source", None)
        act = shots[5]
        climax = shots[6]
        spec = {
            "title": "suse-sex-floor-no-pad",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "heat_scale": "max",
            "spice_level": "extreme",
            "sex_floor_strict": True,
            "sex_vo_strict": False,
            "heat_arc_strict": False,
            "sex_arc_strict": False,
            "sex_wardrobe_strict": False,
            "still_source_strict": False,
            "coitus_strict": False,
            "size_ladder_strict": False,
            "pose_strict": False,
            "montage_strict": False,
            "sex_detail_cu_strict": False,
            "both_undress_strict": False,
            "sex_vo_motion_strict": False,
            "director_intent": {
                "logline": "短 H3 源不可空拉 10 秒槽",
                "tone": "成人",
                "emotional_arc": ["起", "承", "转"],
            },
            "scenes": [{"shots": shots}],
        }
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        msg = str(ctx.exception)
        self.assertIn("HEAT_SEX_DURATION_LOW", msg)
        self.assertIn("Do NOT invent duration_sec=10", msg)
        # Fail-closed: durations must remain source-faithful (not silently padded).
        self.assertAlmostEqual(float(act["duration_sec"]), 5.2, places=2)
        self.assertAlmostEqual(float(climax["duration_sec"]), 5.2, places=2)


class VoWindowTriangleTests(unittest.TestCase):
    """A2 pure helper: tts ≤ cue ≤ slot after offset."""

    def test_ok_triangle(self) -> None:
        ok, code = check_vo_window_triangle(1.5, 0.2, 2.0, 5.2)
        self.assertTrue(ok)
        self.assertEqual(code, "ok")

    def test_cue_exceeds_slot(self) -> None:
        ok, code = check_vo_window_triangle(1.0, 1.0, 5.0, 5.2)
        self.assertFalse(ok)
        self.assertEqual(code, "cue_exceeds_slot")

    def test_tts_exceeds_cue(self) -> None:
        ok, code = check_vo_window_triangle(3.0, 0.0, 2.0, 5.2)
        self.assertFalse(ok)
        self.assertEqual(code, "tts_exceeds_cue")

    def test_slack_allows_tiny_over(self) -> None:
        ok, code = check_vo_window_triangle(2.02, 0.0, 2.0, 5.2, slack_sec=0.03)
        self.assertTrue(ok)
        self.assertEqual(code, "ok")


class BgmSourceHonestyTests(unittest.TestCase):
    """A4: rnb license-only → procedural receipt honesty."""

    def test_mood_library_license_only(self) -> None:
        from sound_plan import mood_library_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mood_dir = root / "rnb"
            mood_dir.mkdir()
            (mood_dir / "rnb_loop_01.wav.license.txt").write_text("cc0\n", encoding="utf-8")
            st = mood_library_status("rnb", skill_root=root)
            self.assertTrue(st["license_only"])
            self.assertEqual(st["wav_count"], 0)

    def test_build_bgm_source_procedural_honest(self) -> None:
        from sound_plan import build_bgm_source_receipt

        rec = build_bgm_source_receipt(
            bed_source="procedural",
            mood="rnb",
            license_note="procedural",
            mood_status={"license_only": True, "wav_count": 0, "mood": "rnb"},
        )
        self.assertTrue(rec["partial"])
        self.assertEqual(rec["bed_source"], "procedural")
        self.assertFalse(rec["licensed_library_used"])
        joined = " ".join(rec["honest_limits"])
        self.assertIn("procedural", joined.lower())
        self.assertIn("license", joined.lower())

    def test_licensed_source_not_partial(self) -> None:
        from sound_plan import build_bgm_source_receipt

        rec = build_bgm_source_receipt(
            bed_source="skill_library",
            mood="rnb",
            license_note="ok",
            music_resolved={"source": "skill_library", "path": "/x/bed.wav"},
            mood_status={"license_only": False, "wav_count": 1},
        )
        self.assertFalse(rec["partial"])
        self.assertTrue(rec["licensed_library_used"])


class OfficialFinalPlateTests(unittest.TestCase):
    """A5: skip gates / red gate-auto → OFFICIAL_FINAL_PLATE, never master_lock."""

    def test_skip_preflight_is_plate(self) -> None:
        from final.delivery_class import classify_official_final

        rep = classify_official_final(skip_preflight=True, final_complete=False)
        self.assertEqual(rep["status"], "OFFICIAL_FINAL_PLATE")
        self.assertTrue(rep["partial"])
        self.assertFalse(rep["master_lock"])
        self.assertIn("skip_preflight", rep["honest_limits"])
        self.assertIn("master_lock", rep["not"])

    def test_gate_auto_red_is_plate(self) -> None:
        from final.delivery_class import classify_official_final

        rep = classify_official_final(gate_auto_ok=False, final_complete=False)
        self.assertEqual(rep["status"], "OFFICIAL_FINAL_PLATE")
        self.assertIn("gate_auto_red", rep["honest_limits"])

    def test_clean_technical_still_not_master(self) -> None:
        from final.delivery_class import classify_official_final

        rep = classify_official_final(
            skip_preflight=False,
            skip_heat_gate=False,
            gate_auto_ok=True,
            final_complete=True,
        )
        self.assertEqual(rep["status"], "TECHNICAL_FINAL")
        self.assertFalse(rep["partial"])
        self.assertFalse(rep["master_lock"])

    def test_delivery_fields_official_final_visibility(self) -> None:
        from final.delivery_class import delivery_fields_from_official_final

        fields = delivery_fields_from_official_final(
            {
                "status": "OFFICIAL_FINAL_PLATE",
                "delivery_class": "OFFICIAL_FINAL_PLATE",
                "delivery_visibility": "visible_plate",
                "master_lock": False,
            }
        )
        self.assertEqual(fields["delivery_class"], "OFFICIAL_FINAL_PLATE")
        self.assertEqual(fields["delivery_source"], "official_final_report")
        self.assertEqual(fields["delivery_visibility"], "visible_plate")
        self.assertFalse(fields["master_lock"])

    def test_delivery_fields_technical_visibility_and_master_lock_passthrough(self) -> None:
        from final.delivery_class import delivery_fields_from_official_final

        fields = delivery_fields_from_official_final(
            {
                "status": "TECHNICAL_FINAL",
                "master_lock": True,
                "delivery_visibility": "technical_final_visible",
            }
        )
        self.assertEqual(fields["delivery_class"], "TECHNICAL_FINAL")
        self.assertEqual(fields["delivery_visibility"], "technical_final_visible")
        self.assertTrue(fields["master_lock"])

    def test_delivery_fields_default_visibility_for_known_status(self) -> None:
        from final.delivery_class import delivery_fields_from_official_final

        plate = delivery_fields_from_official_final({"status": "OFFICIAL_FINAL_PLATE"})
        technical = delivery_fields_from_official_final({"status": "TECHNICAL_FINAL"})
        self.assertEqual(plate["delivery_class"], "OFFICIAL_FINAL_PLATE")
        self.assertEqual(plate["delivery_visibility"], "visible_plate")
        self.assertEqual(technical["delivery_class"], "TECHNICAL_FINAL")
        self.assertEqual(technical["delivery_visibility"], "technical_final_visible")

    def test_write_official_final_report(self) -> None:
        from final.delivery_class import (
            classify_official_final,
            write_official_final_report,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = classify_official_final(skip_preflight=True)
            path = write_official_final_report(root, payload)
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "OFFICIAL_FINAL_PLATE")

    def test_manifest_entry_follows_official_final_fields(self) -> None:
        from post.render_final import build_final_film_manifest_entry

        entry = build_final_film_manifest_entry(
            final_path=Path("/tmp/final.mp4"),
            output_sha256="abc123",
            duration_sec=12.34,
            report_path=Path("/tmp/final-delivery.json"),
            technical_qa={"ok": True},
            official_final={
                "status": "OFFICIAL_FINAL_PLATE",
                "delivery_class": "OFFICIAL_FINAL_PLATE",
                "delivery_visibility": "visible_plate",
                "master_lock": True,
            },
        )
        self.assertEqual(entry["delivery_class"], "OFFICIAL_FINAL_PLATE")
        self.assertEqual(entry["delivery_source"], "official_final_report")
        self.assertEqual(entry["delivery_visibility"], "visible_plate")
        self.assertTrue(entry["master_lock"])


class SexFloorPeelTests(unittest.TestCase):
    """E: sex floor leaf is pure + never pads durations."""

    def test_apply_raises_without_mutating(self) -> None:
        from plan.film_spec_sex_floor import SexFloorError, apply_sex_duration_floor

        rep = {"codes": ["HEAT_SEX_DURATION_LOW"], "sex_duration_ratio": 0.2, "sex_duration_floor": 0.5}
        with self.assertRaises(SexFloorError) as ctx:
            apply_sex_duration_floor(rep, sex_floor_strict=True)
        self.assertIn("Do NOT invent duration_sec=10", str(ctx.exception))

    def test_non_strict_noop(self) -> None:
        from plan.film_spec_sex_floor import apply_sex_duration_floor

        apply_sex_duration_floor(
            {"codes": ["HEAT_SEX_DURATION_LOW"]}, sex_floor_strict=False
        )


class HotpathTimeoutContractTests(unittest.TestCase):
    """D2: critical overnight ffmpeg helpers must pass timeout= to subprocess.run."""

    def test_cosyvoice_ffmpeg_has_timeout(self) -> None:
        path = SCRIPTS / "adapters" / "cosyvoice_tts.py"
        src = path.read_text(encoding="utf-8")
        self.assertIn("timeout=180", src)

    def test_media_qa_run_defaults_timeout(self) -> None:
        path = SCRIPTS / "media" / "media_qa.py"
        src = path.read_text(encoding="utf-8")
        self.assertIn('setdefault("timeout"', src)


class ScaleFallbackTests(unittest.TestCase):
    """B: soft-max / hard-on ban / bare tease ladder."""

    def test_hard_on_ban_after_poison_streak(self) -> None:
        from narrative.scale_fallback import decide_scale_fallback

        d = decide_scale_fallback(
            target_tier="bare",
            consecutive_poison=2,
            consecutive_anatomy_fail=0,
        )
        self.assertEqual(d["action"], "stop_hard_on")
        self.assertIn("SCALE_HARD_ON_BAN", d["codes"])
        self.assertTrue(d["promote_ban"])
        self.assertTrue(d["partial"])
        self.assertNotEqual(d["recommended_tier"], "bare")

    def test_bare_tease_on_penetration_fail(self) -> None:
        from narrative.scale_fallback import decide_scale_fallback

        d = decide_scale_fallback(penetration_failed=True, target_tier="bare")
        self.assertEqual(d["action"], "bare_tease")
        self.assertIn("SCALE_BARE_TEASE_FALLBACK", d["codes"])

    def test_soft_max_when_achieved_below_target(self) -> None:
        from narrative.scale_fallback import decide_scale_fallback

        d = decide_scale_fallback(
            target_tier="bare",
            achieved_tier="soft-max",
        )
        self.assertEqual(d["action"], "accept_soft_max")
        self.assertIn("SCALE_SOFT_MAX", d["codes"])
        self.assertEqual(d["recommended_tier"], "soft-max")

    def test_peak_achieved_and_report(self) -> None:
        from narrative.scale_fallback import report_scale_fallback_for_shots

        shots = [
            {"id": "s1", "wardrobe_state": "full"},
            {"id": "a1", "wardrobe_state": "undressed"},
            {"id": "c1", "wardrobe_state": "soft-max"},
        ]
        rep = report_scale_fallback_for_shots(shots, heat_scale="max")
        self.assertEqual(rep["achieved_wardrobe_tier"], "soft-max")
        self.assertTrue(rep["partial"])
        self.assertIn("SCALE_SOFT_MAX", rep["codes"])
        # S3 · ambition vs honest cap
        self.assertEqual(rep.get("wardrobe_ambition"), "bare")
        self.assertEqual(rep.get("wardrobe_honest_cap"), "soft-max")
        self.assertFalse(rep.get("ambition_met"))

    def test_wardrobe_re_dress_still_hard_in_heat(self) -> None:
        """B3: re-dress still machine-blocked (existing heat code)."""
        from edit_policy_heat import lint_sex_wardrobe

        shots = [
            {
                "id": "a1",
                "heat_phase": "act",
                "wardrobe_state": "undressed",
                "duration_sec": 6,
                "dsl": {"wardrobe_state": "undressed", "action": "thrust"},
            },
            {
                "id": "a2",
                "heat_phase": "act",
                "wardrobe_state": "full",
                "duration_sec": 6,
                "dsl": {"wardrobe_state": "full", "action": "thrust"},
            },
        ]
        try:
            rep = lint_sex_wardrobe(shots, heat_scale="max")
        except TypeError:
            from edit_policy_heat import lint_heat_arc

            rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        codes = rep.get("codes") or []
        self.assertIn(
            "HEAT_WARDROBE_RE_DRESS",
            codes,
            msg=f"expected re-dress code, got {codes}",
        )


class RenderFinalShimContractTests(unittest.TestCase):
    """A3: top-level render_final.py must invoke main under __main__."""

    def test_shim_source_calls_main(self) -> None:
        path = SCRIPTS / "render_final.py"
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        main_guard = False
        calls_main = False
        for node in tree.body:
            if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
                # if __name__ == "__main__":
                left = node.test.left
                if (
                    isinstance(left, ast.Name)
                    and left.id == "__name__"
                    and any(
                        isinstance(c, ast.Constant) and c.value == "__main__"
                        for c in node.test.comparators
                    )
                ):
                    main_guard = True
                    for stmt in node.body:
                        text = ast.dump(stmt)
                        if "main" in text:
                            calls_main = True
        self.assertTrue(main_guard, "render_final.py missing if __name__ == '__main__'")
        self.assertTrue(calls_main, "render_final.py __main__ must call main()")
        self.assertIn("post", src)
        self.assertIn("render_final", src)

    def test_package_main_export(self) -> None:
        from post import render_final as impl

        self.assertTrue(callable(getattr(impl, "main", None)))


if __name__ == "__main__":
    unittest.main()
