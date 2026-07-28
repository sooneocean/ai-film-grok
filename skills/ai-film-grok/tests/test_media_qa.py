from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_qa import (  # noqa: E402
    ALLOWED_VIDEO_ENDPOINTS,
    analyze_media,
    approved_clip_record,
)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class MediaQATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.static = cls.root / "static.mp4"
        cls.slideshow = cls.root / "slideshow.mp4"
        cls.motion = cls.root / "motion.mp4"
        cls.final = cls.root / "final.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=red:s=160x90:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x90:r=24:d=1",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                str(cls.slideshow),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x90:r=24:d=2",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(cls.static),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=160x90:r=24:d=2",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(cls.motion),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(cls.motion),
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(cls.final),
            ],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    @pytest.mark.slow
    def test_static_video_decodes_but_fails_motion_gate(self) -> None:
        qa = analyze_media(self.static, require_audio=False, require_motion=True)
        self.assertTrue(qa["decode_ok"])
        self.assertFalse(qa["motion_ok"])
        self.assertFalse(qa["ok"])

    @pytest.mark.slow
    def test_real_motion_video_passes_decode_duration_and_motion(self) -> None:
        qa = analyze_media(self.motion, require_audio=False, require_motion=True)
        self.assertTrue(qa["ok"], json.dumps(qa, indent=2))
        self.assertGreaterEqual(qa["duration_sec"], 1.9)
        self.assertGreater(qa["decoded_frames"], 20)
        self.assertGreater(qa["motion_score"], 1.0)

    @pytest.mark.slow
    def test_static_slideshow_cannot_pass_on_a_single_large_cut(self) -> None:
        qa = analyze_media(self.slideshow, require_audio=False, require_motion=True)
        self.assertGreater(qa["motion_score"], 1.0)
        self.assertLess(qa["motion_continuity"], qa["motion_continuity_threshold"])
        self.assertFalse(qa["motion_ok"])
        self.assertFalse(qa["ok"])

    @pytest.mark.slow
    def test_formal_final_requires_audio(self) -> None:
        without_audio = analyze_media(self.motion, require_audio=True, require_motion=True)
        with_audio = analyze_media(self.final, require_audio=True, require_motion=True)
        self.assertFalse(without_audio["ok"])
        self.assertIn("audio stream", " ".join(without_audio["errors"]))
        self.assertTrue(with_audio["ok"], json.dumps(with_audio, indent=2))

    @pytest.mark.slow
    def test_video_contract_gate_rejects_small_geometry_and_wrong_fps(self) -> None:
        qa = analyze_media(
            self.motion,
            require_audio=False,
            require_motion=True,
            min_width=704,
            min_height=1280,
            expected_fps=30,
        )
        self.assertFalse(qa["ok"])
        self.assertEqual(qa["width"], 160)
        self.assertEqual(qa["height"], 90)
        self.assertAlmostEqual(qa["fps"], 24.0, places=2)
        self.assertTrue(any("minimum" in error for error in qa["errors"]))
        self.assertTrue(any("fps" in error for error in qa["errors"]))

    @pytest.mark.slow
    def test_clip_approval_requires_endpoint_manual_identity_and_technical_motion(self) -> None:
        qa = analyze_media(self.motion, require_audio=False, require_motion=True)
        valid = {
            "status": "approved",
            "source_endpoint": "image_to_video",
            "identity_approved": True,
            "motion_approved": True,
            "review_note": "Face, wardrobe, and movement checked against the canonical frame.",
            "qa": qa,
        }
        self.assertIn("image_to_video", ALLOWED_VIDEO_ENDPOINTS)
        self.assertTrue(approved_clip_record(valid))
        for key, value in (
            ("source_endpoint", "unknown"),
            ("identity_approved", False),
            ("motion_approved", False),
            ("review_note", ""),
        ):
            candidate = dict(valid)
            candidate[key] = value
            with self.subTest(key=key):
                self.assertFalse(approved_clip_record(candidate))


if __name__ == "__main__":
    unittest.main()
