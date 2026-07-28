from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_sfx_bed import SR, rnb_bgm  # noqa: E402
from music_cue import (  # noqa: E402
    MusicCueError,
    apply_music_timeline_to_samples,
    build_music_timeline,
    motif_seed,
    normalize_music_cue,
    summarize_music_timeline,
)
from render_final import procedural_music  # noqa: E402


def test_music_cue_infers_drama_and_explicit_fields_win() -> None:
    cue = normalize_music_cue(
        {"energy": 0.2, "motif_id": "secret"},
        shot={"dramatic_function": "climax"},
    )
    assert cue["mood"] == "rnb"
    assert cue["energy"] == 0.2
    assert cue["motif_id"] == "secret"


def test_music_cue_infers_semantic_motifs_for_distinct_contexts() -> None:
    assert normalize_music_cue(shot={"dramatic_function": "hook"})["motif_id"] == "arrival:hook"
    assert (
        normalize_music_cue(shot={"dramatic_function": "suspense"})["motif_id"]
        == "tension:suspense"
    )
    assert (
        normalize_music_cue(shot={"dramatic_function": "afterglow"})["motif_id"]
        == "release:afterglow"
    )


def test_music_timeline_keeps_each_shot_even_when_mood_matches() -> None:
    shots = [
        {"id": "s1", "dramatic_function": "afterglow"},
        {"id": "s2", "dramatic_function": "afterglow", "music_cue": {"energy": 0.8}},
    ]
    timeline = build_music_timeline(
        shots, shot_starts={"s1": 0, "s2": 2}, shot_ends={"s1": 2, "s2": 4}
    )
    assert len(timeline) == 2
    assert timeline[0]["energy"] != timeline[1]["energy"]
    summary = summarize_music_timeline(timeline)
    assert summary["bpm_curve"] == [76.0, 76.0]
    assert summary["transitions"] == ["crossfade", "crossfade"]
    assert summary["take_seeds"] == [0, 0]


def test_music_director_reuses_character_or_pair_motif_with_instrumental_palette() -> None:
    shots = [
        {"id": "s1", "dramatic_function": "hook", "characterIds": ["mei"]},
        {"id": "s2", "dramatic_function": "reaction", "characterIds": ["ren", "mei"]},
        {"id": "s3", "dramatic_function": "afterglow", "characterIds": ["mei"]},
    ]
    timeline = build_music_timeline(
        shots, shot_starts={"s1": 0, "s2": 2, "s3": 4}, shot_ends={"s1": 2, "s2": 4, "s3": 6}
    )
    assert [item["motif_id"] for item in timeline] == [
        "character:mei",
        "pair:mei+ren",
        "character:mei",
    ]
    assert all(item["instrumental_only"] for item in timeline)
    assert all(item["instrument_palette"] for item in timeline)
    assert summarize_music_timeline(timeline)["instrumental_only"] is True


def test_instrument_palette_changes_procedural_render_without_changing_motif() -> None:
    base = {
        "start_sec": 0,
        "end_sec": 2,
        "energy": 0.5,
        "motif_id": "character:mei",
        "mood": "warm",
        "bpm": 72,
    }
    piano = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": ["felt_piano"]}]
    )
    strings = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": ["warm_strings"]}]
    )
    assert not np.array_equal(piano, strings)


def test_rnb_palette_is_audible_and_null_palette_is_safe() -> None:
    base = {
        "start_sec": 0,
        "end_sec": 2,
        "energy": 0.5,
        "motif_id": "character:mei",
        "mood": "rnb",
        "bpm": 72,
    }
    rhodes = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": ["rhodes"]}]
    )
    bass = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": ["upright_bass"]}]
    )
    null_palette = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": None}]
    )
    assert not np.array_equal(rhodes, bass)
    assert null_palette.shape == rhodes.shape


@pytest.mark.parametrize(
    ("mood", "palette"),
    [
        ("ambient", "felt_piano"),
        ("ambient", "high_strings"),
        ("ambient", "vibraphone"),
        ("dark", "low_strings"),
        ("dark", "prepared_piano"),
        ("dark", "frame_drum"),
        ("warm", "warm_strings"),
        ("playful", "pizzicato_strings"),
        ("playful", "marimba"),
        ("playful", "brush_drums"),
        ("rnb", "rhodes"),
        ("rnb", "upright_bass"),
        ("rnb", "brush_drums"),
    ],
)
def test_each_exported_instrument_palette_is_audible(mood: str, palette: str) -> None:
    base = {
        "start_sec": 0,
        "end_sec": 2,
        "energy": 0.5,
        "motif_id": "character:mei",
        "mood": mood,
        "bpm": 72,
    }
    plain = procedural_music(2, seed=11, mood_timeline=[base])
    arranged = procedural_music(
        2, seed=11, mood_timeline=[{**base, "instrument_palette": [palette]}]
    )
    assert not np.array_equal(plain, arranged)


def test_music_cue_is_deterministic_and_validates_bounds() -> None:
    assert motif_seed(42, "love", 0) == motif_seed(42, "love", 0)
    with pytest.raises(MusicCueError):
        normalize_music_cue({"brightness": 2})
    with pytest.raises(MusicCueError):
        normalize_music_cue({"take_seed": 2**31})
    with pytest.raises(MusicCueError):
        normalize_music_cue({"motif_role": "random"})


def test_music_cue_marks_dialogue_and_authored_motif_development() -> None:
    cue = normalize_music_cue(
        {
            "motif_role": "reveal",
            "preferred_asset_id": "warm-asset-1",
        },
        shot={"nar": "角色说话"},
    )

    assert cue["dialogue_present"] is True
    assert cue["motif_role"] == "reveal"
    assert cue["preferred_asset_id"] == "warm-asset-1"


def test_music_timeline_automates_supplied_audio() -> None:
    samples = np.ones((400, 2), dtype=np.float64)
    out = apply_music_timeline_to_samples(
        samples,
        sr=100,
        timeline=[
            {"start_sec": 0, "end_sec": 2, "energy": 0.1, "stem_profile": "thin"},
            {"start_sec": 2, "end_sec": 4, "energy": 1.0},
        ],
    )
    assert out.shape == samples.shape
    assert float(out[:200].mean()) < float(out[200:].mean())


def test_bgm_cue_controls_real_low_and_high_layers() -> None:
    quiet = rnb_bgm(4, seed=42, density=0.0, bass_presence=0.0, brightness=0.0)
    full = rnb_bgm(4, seed=42, density=1.0, bass_presence=1.0, brightness=1.0)
    freqs = np.fft.rfftfreq(len(quiet), 1 / SR)
    quiet_fft = np.abs(np.fft.rfft(quiet))
    full_fft = np.abs(np.fft.rfft(full))
    assert full_fft[freqs < 180].mean() > quiet_fft[freqs < 180].mean()
    assert full_fft[freqs > 5000].mean() > quiet_fft[freqs > 5000].mean()


def test_procedural_timeline_honors_mood_bpm_key_and_transition() -> None:
    base = {"start_sec": 0, "end_sec": 2, "energy": 0.5, "motif_id": "same"}
    ambient = procedural_music(
        2, seed=11, mood_timeline=[{**base, "mood": "ambient", "bpm": 54, "key_shift": 0}]
    )
    warm = procedural_music(
        2, seed=11, mood_timeline=[{**base, "mood": "warm", "bpm": 54, "key_shift": 0}]
    )
    shifted = procedural_music(
        2, seed=11, mood_timeline=[{**base, "mood": "warm", "bpm": 54, "key_shift": 7}]
    )
    assert not np.array_equal(ambient, warm)
    assert not np.array_equal(warm, shifted)

    rnb_base = procedural_music(
        2, seed=11, mood_timeline=[{**base, "mood": "rnb", "bpm": 54, "key_shift": 0}]
    )
    rnb_shifted = procedural_music(
        2, seed=11, mood_timeline=[{**base, "mood": "rnb", "bpm": 54, "key_shift": 7}]
    )
    assert not np.array_equal(rnb_base, rnb_shifted)

    rnb_take_two = procedural_music(
        2,
        seed=11,
        mood_timeline=[{**base, "mood": "rnb", "bpm": 54, "key_shift": 0, "seed": 2}],
    )
    assert not np.array_equal(rnb_base, rnb_take_two)

    fade = procedural_music(
        4,
        seed=11,
        mood_timeline=[
            {**base, "mood": "warm", "transition": "crossfade"},
            {**base, "start_sec": 2, "end_sec": 4, "mood": "dark", "transition": "crossfade"},
        ],
    )
    cut = procedural_music(
        4,
        seed=11,
        mood_timeline=[
            {**base, "mood": "warm", "transition": "crossfade"},
            {**base, "start_sec": 2, "end_sec": 4, "mood": "dark", "transition": "cut"},
        ],
    )
    assert not np.array_equal(fade, cut)

    cut_to_silence = procedural_music(
        4,
        seed=11,
        mood_timeline=[
            {**base, "mood": "warm", "transition": "crossfade"},
            {
                **base,
                "start_sec": 2,
                "end_sec": 4,
                "mood": "dark",
                "stem_profile": "silence",
                "transition": "cut",
            },
        ],
    )
    assert not np.any(cut_to_silence[2 * SR :])

    # Crossfade starts at the chapter boundary, never 0.5 seconds before it
    # when a short 2-second chapter has the normal 2.5-second overlap.
    previous_only = procedural_music(
        4,
        seed=11,
        mood_timeline=[
            {**base, "mood": "warm", "transition": "crossfade"},
            {
                **base,
                "start_sec": 2,
                "end_sec": 4,
                "mood": "dark",
                "stem_profile": "silence",
                "transition": "crossfade",
            },
        ],
    )
    assert np.any(previous_only[int(1.75 * SR) : 2 * SR])
