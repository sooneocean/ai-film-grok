from __future__ import annotations

import sys
import hashlib
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scene_sound_stems import _apply_event_controls, render_scene_sound_stem


def test_scene_stem_honors_event_pan_gain_and_fades():
    source = np.ones((10, 2), dtype=np.float32)
    out = _apply_event_controls(
        source,
        {"gain": 0.8, "pan": -0.5, "fade_in_sec": 0.2, "fade_out_sec": 0.2},
        10,
    )
    # Fade starts/ends silent; left receives more energy for a left pan.
    assert np.allclose(out[0], 0.0)
    assert np.allclose(out[-1], 0.0)
    assert out[5, 0] > out[5, 1]


def test_scene_stem_accepts_legacy_local_asset_field(tmp_path: Path):
    asset = tmp_path / "assets" / "tone.wav"
    asset.parent.mkdir()
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    result = render_scene_sound_stem(
        tmp_path,
        {"events": [{"id": "a", "type": "ambience", "asset": "local:assets/tone.wav", "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(), "start_sec": 0, "duration_sec": 0.1}]},
        duration_sec=1,
        out=tmp_path / "audio" / "scene.wav",
        sample_rate=8000,
    )
    assert Path(result["path"]).is_file()
