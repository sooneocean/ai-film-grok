from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from scene_sound_stems import _apply_event_controls


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
