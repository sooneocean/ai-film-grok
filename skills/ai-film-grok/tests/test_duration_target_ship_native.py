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


if __name__ == "__main__":
    unittest.main()
