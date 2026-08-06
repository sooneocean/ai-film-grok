"""Wave D / H1: plate timeout floors, stable SRT paths, mix PARTIAL, plate subs modes."""

from __future__ import annotations

import pytest

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from longform import estimate_plate_timeout  # noqa: E402
from mix_partial import write_final_mix_partial_receipt  # noqa: E402
from render_final import (  # noqa: E402
    RenderError,
    resolve_subtitle_mode,
    stable_path_for_ffmpeg_filter,
)


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

    def test_longform_mode_forces_1800_even_when_duration_short(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps({"production_mode": "longform"}),
                encoding="utf-8",
            )
            n = estimate_plate_timeout(root, duration_sec=60, shot_count=4)
            self.assertGreaterEqual(n, 1800)

    def test_timeout_capped_at_21600(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Huge estimate: 600 + duration*3 + count*20 → force above cap
            n = estimate_plate_timeout(Path(tmp), duration_sec=100_000, shot_count=5000)
            self.assertEqual(n, 21600)


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

    def test_write_final_mix_partial_receipt_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mixed = root / "out" / "mixed.wav"
            mixed.parent.mkdir(parents=True, exist_ok=True)
            mixed.write_bytes(b"RIFF")
            path = write_final_mix_partial_receipt(
                root,
                prior_sc="sidechain_compress",
                error="ffmpeg died: filter graph",
                mixed=mixed,
            )
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "final-mix-partial.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "final-mix-partial")
            self.assertTrue(data["partial"])
            self.assertTrue(data["ok"])
            self.assertEqual(data["from"], "sidechain_compress")
            self.assertEqual(data["to"], "amix_simple")
            self.assertEqual(data["reason"], "sidechain_mix_failed_amix_fallback")
            self.assertIn("ffmpeg died", data["error"])
            self.assertEqual(data["mixed"], str(mixed))
            self.assertIn("at", data)
            self.assertGreaterEqual(int(data["schema_version"]), 1)


class PlateSubsModeTests(unittest.TestCase):
    def test_subs_off_default_for_hf_plate(self) -> None:
        args = argparse.Namespace(subs="off")
        self.assertEqual(resolve_subtitle_mode(args), "off")

    def test_subs_burn_allowed(self) -> None:
        args = argparse.Namespace(subs="burn")
        self.assertEqual(resolve_subtitle_mode(args), "burn")

    def test_subs_invalid_fails_closed(self) -> None:
        args = argparse.Namespace(subs="soft")
        with self.assertRaises(RenderError) as ctx:
            resolve_subtitle_mode(args)
        self.assertIn("burn|off", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
