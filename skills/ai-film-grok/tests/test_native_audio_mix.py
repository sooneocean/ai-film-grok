from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import render_final  # noqa: E402


def test_native_i2v_audio_defaults_to_primary_picture_sound() -> None:
    assert render_final.DEFAULT_NATIVE_AUDIO_VOLUME == 0.72
    assert render_final.DEFAULT_NATIVE_AUDIO_VOLUME > render_final.DEFAULT_MUSIC_VOLUME


def test_cli_native_audio_volume_overrides_voice_track_policy() -> None:
    assert (
        render_final.resolve_native_audio_volume(
            Namespace(native_audio_volume=0.9),
            {"native_audio_volume": 0.72},
            {"native_audio_volume": 0.14},
        )
        == 0.9
    )


def test_primary_native_audio_excludes_measured_near_silence_but_keeps_legacy_stems() -> None:
    assert render_final.primary_native_shot_ids(
        [
            {"id": "shot01", "native_audio": Path("audible.m4a"), "native_audio_audible": True},
            {"id": "shot02", "native_audio": Path("silent.m4a"), "native_audio_audible": False},
            {"id": "shot03", "native_audio": Path("legacy.m4a")},
        ]
    ) == ["shot01", "shot03"]


def test_native_audio_gain_normalizes_audible_stems_without_amplifying_silence() -> None:
    assert render_final.resolve_native_audio_gain({"audible": False, "mean_volume_db": -55}) == 0
    assert render_final.resolve_native_audio_gain({"audible": True, "mean_volume_db": -80}) == 1.6
    assert render_final.resolve_native_audio_gain({"audible": True, "mean_volume_db": -5}) == 0.5
    assert render_final.resolve_native_audio_gain({"audible": True, "mean_volume_db": -22}) == 1.0
    assert render_final.resolve_native_audio_gain({}) == 1.0


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
@pytest.mark.slow
class NativeAudioMixTests(unittest.TestCase):
    @pytest.mark.slow
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
