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
)


def test_music_cue_infers_drama_and_explicit_fields_win() -> None:
    cue = normalize_music_cue(
        {"energy": 0.2, "motif_id": "secret"},
        shot={"dramatic_function": "climax"},
    )
    assert cue["mood"] == "rnb"
    assert cue["energy"] == 0.2
    assert cue["motif_id"] == "secret"


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


def test_music_cue_is_deterministic_and_validates_bounds() -> None:
    assert motif_seed(42, "love", 0) == motif_seed(42, "love", 0)
    with pytest.raises(MusicCueError):
        normalize_music_cue({"brightness": 2})


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
