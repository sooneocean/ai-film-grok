"""Q4.1 duration target honesty + Q5.1 h3 ship-native dry path."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _spec(n_shots: int, dur: float, target: float) -> dict:
    shots = [
        {"id": f"s{i:02d}", "duration_sec": dur, "dramatic_function": "action"}
        for i in range(1, n_shots + 1)
    ]
    return {
        "target_duration": target,
        "scenes": [{"id": "sc01", "shots": shots}],
    }


class TestDurationTarget(unittest.TestCase):
    def test_ok_near_target(self) -> None:
        from plan.duration_target import check_duration_target

        # 12 * 5.2 = 62.4 vs target 60
        r = check_duration_target(_spec(12, 5.2, 60.0))
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "ok")
        self.assertAlmostEqual(r["planned_sum_sec"], 62.4, places=1)

    def test_soft_shortfall(self) -> None:
        from plan.duration_target import check_duration_target

        # 50s planned vs 60 target = 16.7% under → soft (12–20%)
        r = check_duration_target(_spec(10, 5.0, 60.0))
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "soft")
        self.assertIn("DURATION_TARGET_SHORT_SOFT", r["codes"])

    def test_hard_shortfall_savani_pattern(self) -> None:
        from plan.duration_target import check_duration_target, suggest_min_shots

        # 41 * 5.17 ≈ 212 vs 300 = −29%
        r = check_duration_target(_spec(41, 5.17, 300.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["severity"], "hard")
        self.assertIn("DURATION_TARGET_SHORT_HARD", r["codes"])
        self.assertGreaterEqual(r["suggested_min_shots_h3"], 58)
        self.assertEqual(suggest_min_shots(300.0), 58)
        self.assertTrue(any("shots" in n.lower() or "target" in n.lower() for n in r["next"]))

    def test_unset_target_skips(self) -> None:
        from plan.duration_target import check_duration_target

        r = check_duration_target({"scenes": [{"shots": [{"id": "a", "duration_sec": 5}]}]})
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "skip")

    def test_strict_promotes_soft_to_hard(self) -> None:
        from plan.duration_target import check_duration_target

        r = check_duration_target(_spec(10, 5.0, 60.0), strict=True)
        self.assertFalse(r["ok"])
        self.assertEqual(r["severity"], "hard")

    def test_media_short_hard_even_if_planned_ok(self) -> None:
        """Savani pattern: duration_sec padded to target but real clips ~5.2s."""
        from plan.duration_target import check_duration_target

        # planned 41 * ~7.3 ≈ 300; media only 212
        r = check_duration_target(
            _spec(41, 300.0 / 41, 300.0),
            media_sum_sec=211.8,
        )
        self.assertFalse(r["ok"])
        self.assertIn("DURATION_MEDIA_SHORT_HARD", r["codes"])
        # S0.2: also fail on H3-reachable shot density (41 < 58)
        self.assertIn("DURATION_SHOT_COUNT_SHORT_HARD", r["codes"])

    def test_shot_count_short_hard_even_if_planned_padded(self) -> None:
        """S0.2: paper duration_sec cannot hide too few H3 plates."""
        from plan.duration_target import check_duration_target, suggest_min_shots

        # 41 shots × 7.32s planned = 300, but H3 ceiling 41×5.2≈213
        r = check_duration_target(_spec(41, 300.0 / 41, 300.0))
        self.assertFalse(r["ok"])
        self.assertEqual(r["severity"], "hard")
        self.assertIn("DURATION_SHOT_COUNT_SHORT_HARD", r["codes"])
        self.assertEqual(r["suggested_min_shots_h3"], suggest_min_shots(300.0))
        self.assertLess(r["h3_reachable_sec"], 300.0 * 0.8)

    def test_default_duration_sec_is_h3_nominal(self) -> None:
        """S0.1: film_spec default plate matches H3 nominal."""
        from plan.duration_target import H3_NOMINAL_CLIP_SEC
        from plan.film_spec import DEFAULT_DURATION_SEC

        self.assertAlmostEqual(float(DEFAULT_DURATION_SEC), float(H3_NOMINAL_CLIP_SEC), places=2)
        self.assertLessEqual(float(DEFAULT_DURATION_SEC), 5.2 + 1e-6)

    def test_shot_plan_act_climax_capped_at_h3_nominal(self) -> None:
        """S0.1: act/climax no longer invent 8s paper plates."""
        from plan.shot_planning import H3_PLAN_DURATION_CAP_SEC, plan_shots

        beat = {
            "id": "bt01",
            "order": 1,
            "shots_n": 1,
            "targetDuration": 20,
            "dramatic_function": "action",
            "source_text": "沉腰再办。",
            "heat_phase": "act",
            "coitus_beat": "rhythm",
            "wardrobe_state": "bare",
            "objective": "meat",
        }
        scene = {"order": 1, "genre": "adult"}
        shots = plan_shots(
            beat,
            scene=scene,
            shot_counter_start=1,
            character_ids=["heroine"],
            location_id="room",
            chain_continue=False,
        )
        self.assertTrue(shots)
        for sh in shots:
            film = sh.get("_film") or {}
            d = float(film.get("duration_sec") or 0)
            self.assertLessEqual(d, float(H3_PLAN_DURATION_CAP_SEC) + 1e-6, film)


class TestCropMasterStill(unittest.TestCase):
    def test_clean_stills_ok(self) -> None:
        from assets.still_uniqueness import crop_master_still_report

        man = {
            "stills": {
                f"s{i:02d}": {
                    "status": "approved",
                    "path": f"keyframes/s{i:02d}.png",
                    "sha256": f"abc{i}",
                }
                for i in range(1, 6)
            }
        }
        r = crop_master_still_report(man)
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "ok")

    def test_dominant_crop_master_hard(self) -> None:
        from assets.still_uniqueness import crop_master_still_report

        man = {
            "stills": {
                f"s{i:02d}": {
                    "status": "approved",
                    "path": f"keyframes/crop-master_s{i:02d}.png",
                    "note": "ffmpeg crop from cast master",
                    "sha256": f"crop{i}",
                }
                for i in range(1, 8)
            }
        }
        r = crop_master_still_report(man, min_shots=4)
        self.assertFalse(r["ok"])
        self.assertEqual(r["severity"], "hard")
        self.assertIn("STILL_CROP_MASTER_DOMINANT", r["codes"])

    def test_parent_sha_mass_soft(self) -> None:
        from assets.still_uniqueness import crop_master_still_report

        # 4 share parent_sha (mass group) + 4 clean → 50% → soft (default hard 55%)
        man = {
            "stills": {
                **{
                    f"s{i:02d}": {
                        "status": "approved",
                        "path": f"keyframes/s{i:02d}.png",
                        "parent_sha256": "MASTERSHA",
                        "sha256": f"var{i}",
                    }
                    for i in range(1, 5)
                },
                **{
                    f"s{i:02d}": {
                        "status": "approved",
                        "path": f"keyframes/unique_{i:02d}.png",
                        "sha256": f"uniq{i}",
                    }
                    for i in range(5, 9)
                },
            }
        }
        r = crop_master_still_report(man, soft_ratio=0.35, hard_ratio=0.55, min_shots=4)
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "soft")
        self.assertIn("STILL_CROP_MASTER_WARN", r["codes"])


class TestShipNativeDry(unittest.TestCase):
    def test_dry_run_writes_receipt(self) -> None:
        import tempfile

        from media.h3_ship_native import ship_native

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clips").mkdir()
            # minimal mp4-like empty not ok — dry_run never opens ffmpeg
            # but still needs files on disk for path resolution
            for i in range(1, 3):
                p = root / "clips" / f"s{i:02d}.mp4"
                p.write_bytes(b"\x00" * 64)
            spec = {
                "target_duration": 30.0,
                "scenes": [
                    {
                        "shots": [
                            {"id": "s01", "duration_sec": 5.0},
                            {"id": "s02", "duration_sec": 5.0},
                        ]
                    }
                ],
            }
            man = {
                "clips": {
                    "s01": {"status": "approved", "path": "clips/s01.mp4"},
                    "s02": {"status": "approved", "path": "clips/s02.mp4"},
                }
            }
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            (root / "receipts").mkdir()
            rep = ship_native(root, dry_run=True)
            self.assertTrue(rep["ok"])
            self.assertTrue(rep.get("dry_run"))
            self.assertEqual(rep["delivery_class"], "OFFICIAL_FINAL_PLATE")
            self.assertFalse(rep.get("master_lock"))
            self.assertEqual(rep["clip_count"], 2)
            # planned 10s vs 30s → hard shortfall flagged in duration_target subreport
            dt = rep.get("duration_target") or {}
            self.assertIn("DURATION_TARGET_SHORT_HARD", dt.get("codes") or [])
            rec = root / "receipts" / "h3-ship-native.json"
            self.assertTrue(rec.is_file())
            # S1.1: default still documents stage-2 final path
            st2 = rep.get("stage2") or {}
            self.assertFalse(st2.get("concat_includes_hardburn"))
            self.assertIn("aifilm final", st2.get("command") or "")

    def test_caption_music_flags_stage2_only(self) -> None:
        """S1.1: caption/music-mood do not claim burned plate."""
        import tempfile

        from media.h3_ship_native import ship_native

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "clips").mkdir()
            p = root / "clips" / "s01.mp4"
            p.write_bytes(b"\x00" * 64)
            spec = {
                "target_duration": 5.0,
                "scenes": [{"shots": [{"id": "s01", "duration_sec": 5.0}]}],
            }
            man = {"clips": {"s01": {"status": "approved", "path": "clips/s01.mp4"}}}
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            (root / "receipts").mkdir()
            rep = ship_native(
                root, dry_run=True, caption="hardburn", music_mood="rnb"
            )
            self.assertTrue(rep["ok"])
            st2 = rep.get("stage2") or {}
            self.assertTrue(st2.get("requested"))
            self.assertFalse(st2.get("concat_includes_hardburn"))
            self.assertFalse(st2.get("concat_includes_bgm"))
            self.assertIn("ship_hardburn", st2.get("command") or "")
            self.assertIn("--music-mood rnb", st2.get("command") or "")
            self.assertEqual(rep["delivery_class"], "OFFICIAL_FINAL_PLATE")

    def test_mandarin_unverified_soft_and_hard_flag(self) -> None:
        """S1.3: aac present → MANDARIN_UNVERIFIED soft; hard env promotes stream fail."""
        from pathlib import Path
        from unittest import mock

        from media.h3_ship_native import sample_native_audio_audit

        with mock.patch("media.h3_ship_native._ffprobe_has_audio", return_value=True), mock.patch(
            "media.h3_ship_native._mean_volume_db", return_value=-20.0
        ):
            r = sample_native_audio_audit(
                ["s01"], [Path("/tmp/x.mp4")], sample_n=1, mandarin_hard=False
            )
        self.assertTrue(r["ok"])
        self.assertEqual(r["severity"], "soft")
        self.assertIn("NATIVE_AUDIO_MANDARIN_UNVERIFIED", r["codes"])
        self.assertTrue(r.get("listen_checklist"))

        with mock.patch("media.h3_ship_native._ffprobe_has_audio", return_value=False), mock.patch(
            "media.h3_ship_native._mean_volume_db", return_value=None
        ):
            r2 = sample_native_audio_audit(
                ["s01"], [Path("/tmp/x.mp4")], sample_n=1, mandarin_hard=True
            )
        self.assertFalse(r2["ok"])
        self.assertEqual(r2["severity"], "hard")
        self.assertIn("NATIVE_AUDIO_MANDARIN_HARD", r2["codes"])


class TestPlateVsMaster(unittest.TestCase):
    def test_plate_blocks_final_complete_claim(self) -> None:
        """S1.4: OFFICIAL_FINAL_PLATE + final_complete → blocks ship complete."""
        import json
        import tempfile

        from final.delivery_class import plate_blocks_final_complete

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "receipts").mkdir()
            (root / "receipts" / "official-final-report.json").write_text(
                json.dumps(
                    {
                        "status": "OFFICIAL_FINAL_PLATE",
                        "partial": True,
                        "master_lock": False,
                    }
                ),
                encoding="utf-8",
            )
            r = plate_blocks_final_complete(root, gates={"final_complete": True})
            self.assertFalse(r["ok"])
            self.assertTrue(r["blocks_ship_complete"])
            self.assertIn("PLATE_CLAIMED_FINAL_COMPLETE", r["codes"])


if __name__ == "__main__":
    unittest.main()
