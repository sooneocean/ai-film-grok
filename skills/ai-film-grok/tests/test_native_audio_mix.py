from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_final  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class NativeAudioMixTests(unittest.TestCase):
    def test_native_track_aligns_stems_and_silence_to_full_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            audio = root / "audio"
            work.mkdir()
            audio.mkdir()
            stem = root / "native.m4a"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-c:a",
                    "aac",
                    str(stem),
                ],
                check=True,
                capture_output=True,
            )
            track = render_final.build_native_track(
                [
                    {"id": "shot01", "target": 2.0, "native_audio": stem},
                    {"id": "shot02", "target": 1.5, "native_audio": None},
                ],
                title_duration=0.5,
                end_duration=0.5,
                work=work,
                audio_dir=audio,
                transition_sec=0.0,  # hard-cut timeline
            )
            self.assertTrue(track.is_file())
            self.assertAlmostEqual(render_final.pdur(track), 4.5, delta=0.1)


if __name__ == "__main__":
    unittest.main()
