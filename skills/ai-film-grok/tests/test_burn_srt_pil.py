"""Tests for burn_srt_pil.py — the P0 PIL caption burn recovery path.

This module had ZERO direct test coverage despite being the P0 recovery
when HyperFrames fails to burn subtitles (lessons-2026-07-23-subs-always-burn-hard.md).

Tests cover:
  - parse_srt: SRT parsing (timestamps, multi-line cues, edge cases)
  - main(): end-to-end burn (requires ffmpeg + PIL)

The end-to-end tests use @skipUnless(ffmpeg) to skip on CI without ffmpeg.
"""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import burn_srt_pil  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class TestParseTs(unittest.TestCase):
    """_parse_ts converts SRT timestamp to seconds."""

    def test_simple(self):
        self.assertAlmostEqual(burn_srt_pil._parse_ts("00:00:01,500"), 1.5)

    def test_zero(self):
        self.assertAlmostEqual(burn_srt_pil._parse_ts("00:00:00,000"), 0.0)

    def test_minutes_seconds(self):
        self.assertAlmostEqual(burn_srt_pil._parse_ts("00:01:30,000"), 90.0)

    def test_hours(self):
        self.assertAlmostEqual(burn_srt_pil._parse_ts("01:00:00,000"), 3600.0)

    def test_milliseconds_variable_width(self):
        # SRT uses comma for decimal; ms can be 1-3 digits
        self.assertAlmostEqual(burn_srt_pil._parse_ts("00:00:02,50"), 2.5)


class TestParseSrt(unittest.TestCase):
    """parse_srt extracts cues from SRT text."""

    def test_single_cue(self):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nHello world\n"
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(len(cues), 1)
        self.assertAlmostEqual(cues[0]["start"], 1.0)
        self.assertAlmostEqual(cues[0]["end"], 3.0)
        self.assertEqual(cues[0]["text"], "Hello world")

    def test_multiple_cues(self):
        srt = (
            "1\n00:00:01,000 --> 00:00:03,000\nFirst\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond\n"
        )
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["text"], "First")
        self.assertEqual(cues[1]["text"], "Second")

    def test_multiline_body(self):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two\n"
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(len(cues), 1)
        self.assertIn("Line one", cues[0]["text"])
        self.assertIn("Line two", cues[0]["text"])

    def test_empty_srt(self):
        cues = burn_srt_pil.parse_srt("")
        self.assertEqual(cues, [])

    def test_whitespace_only_blocks_skipped(self):
        srt = "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n\n\n"
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(len(cues), 1)

    def test_block_without_arrow_skipped(self):
        srt = "1\n00:00:01,000 - 00:00:03,000\nNo arrow\n"
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(cues, [])

    def test_chinese_text(self):
        """Chinese caption text preserved correctly."""
        srt = "1\n00:00:01,000 --> 00:00:03,000\n你好世界\n"
        cues = burn_srt_pil.parse_srt(srt)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["text"], "你好世界")


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg + ffprobe required for burn tests")
class TestBurnEndToEnd(unittest.TestCase):
    """End-to-end: burn SRT into a real video and verify output.

    These tests generate a tiny black video with ffmpeg, burn a subtitle
    cue into it, and verify the output file is a valid mp4 with different
    pixels than the input (proving the overlay was applied).
    """

    @classmethod
    def setUpClass(cls):
        import tempfile

        cls.tmpdir = tempfile.mkdtemp()
        cls.input_video = Path(cls.tmpdir) / "input.mp4"
        cls.srt_file = Path(cls.tmpdir) / "test.srt"
        cls.output_video = Path(cls.tmpdir) / "output.mp4"

        # Generate a 3-second black 720x1280 video
        import subprocess

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=720x1280:d=3",
                "-pix_fmt",
                "yuv420p",
                str(cls.input_video),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )

        # Write a simple SRT with one cue covering the full duration
        cls.srt_file.write_text(
            "1\n00:00:00,500 --> 00:00:02,500\n测试字幕\n",
            encoding="utf-8",
        )

        # Burn once in setUpClass so both tests share the same output
        from unittest import mock

        argv = [
            "--video",
            str(cls.input_video),
            "--srt",
            str(cls.srt_file),
            "--out",
            str(cls.output_video),
            "--batch",
            "8",
        ]
        with mock.patch.object(sys, "argv", ["burn_srt_pil.py", *argv]):
            rc = burn_srt_pil.main()
        assert rc == 0, f"setUpClass burn failed with rc={rc}"

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_burn_produces_valid_mp4(self):
        """Burned output is a valid non-trivial mp4 file."""
        self.assertTrue(self.output_video.is_file())
        self.assertGreater(
            self.output_video.stat().st_size,
            100,
            "output video too small — burn may have failed silently",
        )

    def test_burn_changes_pixels(self):
        """Burned video bottom-band has higher contrast than plain black.

        The subtitle overlay adds white text glyphs to the bottom band,
        so the pixel variance should be higher than a plain black frame.
        """
        import subprocess

        from PIL import Image

        # Extract a frame from the middle of the burned video
        frame = Path(self.tmpdir) / "frame_burned.png"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                "1.5",
                "-i",
                str(self.output_video),
                "-frames:v",
                "1",
                str(frame),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"ffmpeg frame extract failed: {proc.stderr[-500:]}")
        self.assertTrue(frame.is_file())

        im = Image.open(frame).convert("L")
        w, h = im.size
        # Bottom 14% band
        band = im.crop((0, int(h * 0.86), w, h))
        lo, hi = band.getextrema()
        contrast = hi - lo
        # Plain black frame has contrast 0; burned subtitles raise it significantly
        self.assertGreater(
            contrast,
            30,
            f"bottom-band contrast {contrast} too low — subtitle may not be burned in",
        )


if __name__ == "__main__":
    unittest.main()
