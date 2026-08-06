"""Fail-loud media duration helpers (no silent fake defaults)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_duration import MediaDurationError, probe_duration_sec  # noqa: E402


@pytest.mark.slow
class MediaDurationTests(unittest.TestCase):
    @pytest.mark.slow
    def test_missing_path_raises(self) -> None:
        with self.assertRaises(MediaDurationError) as ctx:
            probe_duration_sec("/nonexistent/path/nope.mp4", label="unit")
        self.assertIn("missing", str(ctx.exception).lower())

    @pytest.mark.slow
    def test_empty_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "empty.mp4"
            p.write_bytes(b"")
            with self.assertRaises(MediaDurationError) as ctx:
                probe_duration_sec(p, label="unit")
            msg = str(ctx.exception).lower()
            self.assertTrue("empty" in msg or "0 bytes" in msg)

    @pytest.mark.slow
    def test_garbage_file_raises_not_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "garbage.mp4"
            p.write_bytes(b"not a real media file at all")
            with self.assertRaises(MediaDurationError):
                probe_duration_sec(p, label="unit")

    @pytest.mark.slow
    def test_real_wav_has_positive_duration(self) -> None:
        """Drive real ffprobe on a tiny generated wav — proves shipped helper works."""
        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "tone.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=0.35",
                    "-ar",
                    "16000",
                    str(wav),
                ],
                check=True,
                capture_output=True,
            )
            dur = probe_duration_sec(wav, label="unit-wav")
            self.assertGreater(dur, 0.2)
            self.assertLess(dur, 1.0)

    @pytest.mark.slow
    def test_render_final_pdur_missing_raises(self) -> None:
        """Shipped render_final.pdur must not return a silent numeric default."""
        import render_final as rf

        with self.assertRaises(Exception) as ctx:
            rf.pdur("/nonexistent/clip-xyz.mp4")
        # RenderError or MediaDurationError wrapped
        self.assertTrue(str(ctx.exception))
        # must not have returned a float
        self.assertNotIsInstance(ctx.exception, (float, int))


if __name__ == "__main__":
    unittest.main()
