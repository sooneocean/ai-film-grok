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


def test_native_i2v_audio_can_supply_picture_sound_when_no_tts_is_rendered() -> None:
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


def test_primary_native_audio_excludes_silence_and_tts_replaced_stems() -> None:
    assert render_final.primary_native_shot_ids(
        [
            {"id": "shot01", "native_audio": Path("audible.m4a"), "native_audio_audible": True},
            {"id": "shot02", "native_audio": Path("silent.m4a"), "native_audio_audible": False},
            {"id": "shot03", "native_audio": Path("legacy.m4a")},
            {
                "id": "shot04",
                "native_audio": Path("spoken-native.m4a"),
                "native_audio_audible": True,
                "native_audio_suppressed_for_tts": True,
            },
        ]
    ) == ["shot01", "shot03"]


def test_only_explicit_post_tts_dialogue_replaces_native_audio() -> None:
    native_dialogue = {
        "dialogue_contracts": [
            {
                "lines": [
                    {
                        "audio_origin": "native",
                        "lipsync_evidence": {"method": "generated_native_audio"},
                    }
                ]
            }
        ]
    }
    assert render_final.native_dialogue_replaced_by_post_tts(native_dialogue) is False
    assert render_final.native_dialogue_replaced_by_post_tts({"dialogue_contracts": []}) is False
    assert (
        render_final.native_dialogue_replaced_by_post_tts(
            {
                "dialogue_contracts": [
                    {"lines": [{"audio_origin": "post_vo", "lipsync_evidence": {}}]}
                ]
            }
        )
        is True
    )


def test_resolve_dialogue_audio_lane_xor() -> None:
    from final.native_audio import (
        dialogue_lane_suppresses_native,
        dialogue_lane_tts_mix_gain,
        resolve_dialogue_audio_lane,
    )

    spoken = {"dialogue": "你好"}
    # Audible native + spoken → native (no Edge double-speak)
    assert (
        resolve_dialogue_audio_lane(
            spoken,
            has_native_stem=True,
            native_audible=True,
            has_spoken_text=True,
        )
        == "native"
    )
    # Explicit post_vo wins
    assert (
        resolve_dialogue_audio_lane(
            {
                "dialogue": "你好",
                "dialogue_contracts": [{"lines": [{"audio_origin": "post_vo"}]}],
            },
            has_native_stem=True,
            native_audible=True,
            has_spoken_text=True,
        )
        == "post_tts"
    )
    # No native → post_tts
    assert (
        resolve_dialogue_audio_lane(
            spoken,
            has_native_stem=False,
            native_audible=None,
            has_spoken_text=True,
        )
        == "post_tts"
    )
    # Explicit strip policy
    assert (
        resolve_dialogue_audio_lane(
            spoken,
            has_native_stem=True,
            native_audible=True,
            has_spoken_text=True,
            audio_policy="strip_native_use_tts_bgm",
        )
        == "post_tts"
    )
    # Silence inaudible native falls back to TTS
    assert (
        resolve_dialogue_audio_lane(
            spoken,
            has_native_stem=True,
            native_audible=False,
            has_spoken_text=True,
        )
        == "post_tts"
    )
    # Coverage plate
    assert (
        resolve_dialogue_audio_lane(
            {"screen_mode": "reaction"},
            has_native_stem=True,
            native_audible=True,
            has_spoken_text=False,
            non_vo_coverage=True,
        )
        == "silence"
    )
    assert dialogue_lane_tts_mix_gain("native") == 0.0
    assert dialogue_lane_tts_mix_gain("post_tts") == 1.0
    assert dialogue_lane_suppresses_native("post_tts") is True
    assert dialogue_lane_suppresses_native("native") is False


def test_primary_native_and_tts_not_both() -> None:
    """Bookkeeping: native lane never reports TTS mix gain."""
    from final.native_audio import dialogue_lane_tts_mix_gain, resolve_dialogue_audio_lane

    lane = resolve_dialogue_audio_lane(
        {"dialogue": "重复对白禁止"},
        has_native_stem=True,
        native_audible=True,
        has_spoken_text=True,
    )
    assert lane == "native"
    assert dialogue_lane_tts_mix_gain(lane) == 0.0
    # post_tts path suppresses native in primary_native_shot_ids
    shots = [
        {
            "id": "s1",
            "native_audio": Path("a.m4a"),
            "native_audio_audible": True,
            "native_audio_suppressed_for_tts": False,
            "dialogue_audio_lane": "native",
            "tts_mix_gain": 0.0,
        },
        {
            "id": "s2",
            "native_audio": Path("b.m4a"),
            "native_audio_audible": True,
            "native_audio_suppressed_for_tts": True,
            "dialogue_audio_lane": "post_tts",
            "tts_mix_gain": 1.0,
        },
    ]
    assert render_final.primary_native_shot_ids(shots) == ["s1"]


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
