"""Unit tests for composition anti-hijack (synthetic frames, no ffmpeg)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from composition_anti_hijack import (  # noqa: E402
    infer_want,
    score_frame_array,
)


def _face_frame() -> np.ndarray:
    """Warm skin center, varied top (hair/sky) — should pass female_face."""
    im = np.zeros((128, 96, 3), dtype=np.uint8)
    # top: darkish varied
    im[:40] = [40, 35, 30]
    im[10:30, 30:60] = [20, 15, 10]
    # center warm skin
    im[40:100, 25:70] = [180, 130, 100]
    im[50:70, 35:55] = [200, 150, 120]
    # add noise for cstd
    rng = np.random.default_rng(0)
    im = np.clip(im.astype(np.int16) + rng.integers(-20, 20, im.shape), 0, 255).astype(np.uint8)
    return im


def _sand_frame() -> np.ndarray:
    """Bright uniform beige top + low detail center — footprints/aerial hijack."""
    im = np.zeros((128, 96, 3), dtype=np.uint8)
    im[:] = [190, 175, 150]
    im[:64] = [200, 185, 160]
    return im


def _torso_frame() -> np.ndarray:
    """Dark top (hairless/no face), bright mid chest plate."""
    im = np.zeros((128, 96, 3), dtype=np.uint8)
    im[:30] = [40, 30, 25]
    im[40:100, 20:76] = [170, 140, 120]
    return im


def test_face_scores_high():
    s = score_frame_array(_face_frame(), want="female_face")
    assert s["skin"] > 0.15
    assert s["hijack"] is False
    assert s["score"] >= 0.45


def test_sand_is_hijack_for_face():
    s = score_frame_array(_sand_frame(), want="female_face")
    assert s["sandish"] >= 0.5 or s["hijack"] is True
    assert s["hijack"] is True
    assert s["score"] < 0.45


def test_torso_is_hijack_for_ms():
    s = score_frame_array(_torso_frame(), want="female_ms_two")
    assert s["torso_risk"] >= 0.5 or s["hijack"] is True
    assert s["hijack"] is True


def test_infer_want_dialogue_cu():
    shot = {
        "id": "ep02_sc01_sh01",
        "shot_size": "cu",
        "spoken_text": "你好",
        "audio_cues": [{"spoken_text": "你好", "speaker": "澜汐"}],
        "focal_character": "澜汐",
        "dsl": {"camera": {"shot_size": "cu"}, "subject": "澜汐"},
    }
    assert infer_want(shot) == "female_face"


def test_apply_demotes_hijack_without_video(monkeypatch, tmp_path):
    """apply_anti_hijack_to_candidates should rank clean above hijack via mocked score_take."""
    import composition_anti_hijack as ah

    def fake_score(path, want="generic", cache_dir=None, t_sec=1.2, t0_sec=0.1):
        if "sand" in str(path):
            return {
                "path": str(path),
                "ok": False,
                "hijack": True,
                "score": -0.2,
                "sandish": 1.0,
                "skin": 0.0,
                "torso_risk": 0.0,
                "want": want,
            }
        return {
            "path": str(path),
            "ok": True,
            "hijack": False,
            "score": 1.0,
            "sandish": 0.0,
            "skin": 1.0,
            "torso_risk": 0.0,
            "want": want,
        }

    monkeypatch.setattr(ah, "score_take", fake_score)
    cands = [
        {"path": "/tmp/sand_take.mp4", "mean": 40.0, "bytes": 9_000_000, "score": 40.0},
        {"path": "/tmp/face_take.mp4", "mean": 18.0, "bytes": 8_000_000, "score": 18.0},
    ]
    out = ah.apply_anti_hijack_to_candidates(
        cands,
        shot={"spoken_text": "x", "shot_size": "cu", "dsl": {"camera": {"shot_size": "cu"}}},
        want="female_face",
    )
    assert out[0]["path"].endswith("face_take.mp4")
    assert out[0]["composition_hijack"] is False
    assert out[1]["composition_hijack"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
