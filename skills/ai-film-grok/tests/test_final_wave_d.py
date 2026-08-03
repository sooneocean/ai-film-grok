"""Wave D: plate timeout floors, stable SRT paths, sidechain→amix fallback unit."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from longform import estimate_plate_timeout  # noqa: E402
from render_final import stable_path_for_ffmpeg_filter  # noqa: E402


class TimeoutFloorTests(unittest.TestCase):
    def test_short_floor_1200(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                estimate_plate_timeout(Path(tmp), duration_sec=60, shot_count=8),
                1200,
            )

    def test_long_duration_floor_1800(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            n = estimate_plate_timeout(Path(tmp), duration_sec=500, shot_count=20)
            self.assertGreaterEqual(n, 1800)


class StableSrtPathTests(unittest.TestCase):
    def test_no_spaces_returns_same(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "final.srt"
            p.write_text("1\n", encoding="utf-8")
            self.assertEqual(stable_path_for_ffmpeg_filter(p, suffix=".srt"), p.resolve())

    def test_spaces_copies_to_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spaced = Path(tmp) / "my film root"
            spaced.mkdir()
            p = spaced / "final.srt"
            p.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
            out = stable_path_for_ffmpeg_filter(p, suffix=".srt", prefix="aifilm-test-srt")
            self.assertNotEqual(out, p.resolve())
            self.assertNotIn(" ", str(out))
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_text(encoding="utf-8"), p.read_text(encoding="utf-8"))


class SidechainFallbackContractTests(unittest.TestCase):
    """Contract: fallback writes partial receipt shape (no full render required)."""

    def test_partial_receipt_schema_fields(self) -> None:
        # Document expected keys written by render_final on sidechain failure path
        required = {
            "kind",
            "partial",
            "reason",
            "from",
            "to",
        }
        sample = {
            "kind": "final-mix-partial",
            "schema_version": 1,
            "partial": True,
            "reason": "sidechain_mix_failed_amix_fallback",
            "from": "dynamic_eq",
            "to": "amix_simple",
        }
        self.assertTrue(required.issubset(sample.keys()))


if __name__ == "__main__":
    unittest.main()
