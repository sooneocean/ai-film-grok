"""VO atempo fit-to-plate (cn three-axis) — pure plan + real ffmpeg fit."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from vo_atempo import (  # noqa: E402
    VoAtempoError,
    atempo_filter_chain,
    fit_voice_to_plate,
    plan_vo_atempo,
)


class PlanVoAtempoTests(unittest.TestCase):
    def test_speed_up_when_vo_longer_than_plate(self) -> None:
        # 5s VO → 4s plate → atempo = 1.25
        plan = plan_vo_atempo(5.0, 4.0)
        self.assertTrue(plan["ok"])
        self.assertAlmostEqual(plan["atempo"], 5.0 / 4.0, places=4)
        self.assertGreater(plan["atempo"], 1.0)
        self.assertAlmostEqual(plan["fitted_sec"], 4.0, places=2)
        self.assertEqual(plan["out_sec"], 4.0)
        self.assertIn(plan["mode"], {"atempo", "atempo_pad"})

    def test_short_vo_pads_instead_of_dragging_speech(self) -> None:
        # 4s VO → 6s plate: drag guard → atempo=1.0 + silence pad (not 0.667 slow)
        plan = plan_vo_atempo(4.0, 6.0)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["mode"], "pad_natural")
        self.assertTrue(plan.get("drag_guard"))
        self.assertAlmostEqual(plan["atempo"], 1.0, places=3)
        self.assertAlmostEqual(plan["fitted_sec"], 4.0, places=2)
        self.assertAlmostEqual(plan["pad_sec"], 2.0, places=2)
        self.assertAlmostEqual(plan["out_sec"], 6.0, places=3)

    def test_mild_slow_still_allowed_near_plate(self) -> None:
        # 5.7s VO on 6s plate → raw≈0.95 ≥ 0.92 → small atempo ok
        plan = plan_vo_atempo(5.7, 6.0)
        self.assertTrue(plan["ok"])
        self.assertFalse(plan.get("drag_guard"))
        self.assertGreaterEqual(plan["atempo"], 0.92 - 1e-6)
        self.assertLessEqual(plan["atempo"], 1.0 + 1e-6)

    def test_allow_speech_drag_opt_in(self) -> None:
        plan = plan_vo_atempo(4.0, 6.0, allow_speech_drag=True)
        self.assertTrue(plan["ok"])
        self.assertLess(plan["atempo"], 1.0)
        self.assertFalse(plan.get("drag_guard"))

    def test_identity_when_close(self) -> None:
        plan = plan_vo_atempo(6.0, 6.0)
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["mode"], "identity")
        self.assertAlmostEqual(plan["atempo"], 1.0, places=2)

    def test_fail_when_needs_more_than_max_atempo(self) -> None:
        # 10s VO on 6s plate needs ~1.67 > 1.5
        plan = plan_vo_atempo(10.0, 6.0, max_atempo=1.5)
        self.assertFalse(plan["ok"])
        self.assertEqual(plan["mode"], "fail_over")
        self.assertIn("cannot fit", plan["note"].lower())

    def test_direction_od_over_target(self) -> None:
        """Critical cn lesson: factor = vo/plate (not plate/vo)."""
        plan = plan_vo_atempo(8.0, 6.0)
        self.assertTrue(plan["ok"])
        self.assertAlmostEqual(plan["raw_atempo"], 8.0 / 6.0, places=4)
        # fitted = vo/factor ≈ plate
        self.assertAlmostEqual(plan["fitted_sec"], 8.0 / plan["atempo"], places=3)

    def test_atempo_filter_chain_single(self) -> None:
        f = atempo_filter_chain(1.25)
        self.assertIn("atempo=1.25", f)


class FitVoiceToPlateFfmpegTests(unittest.TestCase):
    def _sine(self, path: Path, sec: float) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={sec}",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def test_fit_short_vo_to_longer_plate(self) -> None:
        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg missing")
        from media_duration import probe_duration_sec

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "vo.wav"
            out = root / "fit.wav"
            self._sine(src, 0.40)
            plan = fit_voice_to_plate(src, out, plate_sec=0.60, vo_sec=0.40)
            self.assertTrue(plan["ok"])
            self.assertTrue(out.is_file())
            dur = probe_duration_sec(out, label="fit-out")
            self.assertAlmostEqual(dur, 0.60, delta=0.08)

    def test_fit_long_vo_speeds_up_to_plate(self) -> None:
        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg missing")
        from media_duration import probe_duration_sec

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "vo.wav"
            out = root / "fit.wav"
            self._sine(src, 0.55)
            plan = fit_voice_to_plate(src, out, plate_sec=0.45, vo_sec=0.55)
            self.assertTrue(plan["ok"])
            self.assertGreater(plan["atempo"], 1.0)
            dur = probe_duration_sec(out, label="fit-out")
            self.assertAlmostEqual(dur, 0.45, delta=0.08)

    def test_fit_raises_when_impossible(self) -> None:
        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg missing")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "vo.wav"
            out = root / "fit.wav"
            self._sine(src, 1.0)
            with self.assertRaises(VoAtempoError):
                fit_voice_to_plate(src, out, plate_sec=0.4, vo_sec=1.0, max_atempo=1.5)


if __name__ == "__main__":
    unittest.main()
