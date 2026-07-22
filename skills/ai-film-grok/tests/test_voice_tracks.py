#!/usr/bin/env python3
"""Unit tests for multi-track voice layer (nar / vocal_color / tone / sfx)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from voice_tracks import (  # noqa: E402
    apply_voice_tracks_to_spec,
    compute_color_offset_sec,
    pick_auto_vocal_color,
    resolve_shot_vocal_color,
    resolve_voice_tracks,
    sound_cues_to_sfx_kinds,
    tone_tags_to_prompt,
)


class VoiceTracksTest(unittest.TestCase):
    def test_tone_tags_to_prompt(self) -> None:
        line = tone_tags_to_prompt(["breathy", "teasing"])
        self.assertIn("Performance tone", line)
        self.assertIn("breathy", line.lower())

    def test_sound_cues_map(self) -> None:
        kinds = sound_cues_to_sfx_kinds(["breath", "leather", "impact", "unknown_xyz"])
        self.assertIn("breath", kinds)
        self.assertIn("impact", kinds)
        self.assertIn("generic", kinds)

    def test_auto_color_by_phase(self) -> None:
        shot = {"id": "shot06", "heat_phase": "act"}
        text = pick_auto_vocal_color(shot, seed=1)
        self.assertTrue(len(text) >= 1)

    def test_resolve_author_color_requires_opt_in(self) -> None:
        # default off — author color ignored unless tracks enabled + gain > 0
        policy = resolve_voice_tracks({"heat_scale": "max"})
        self.assertFalse(policy["enabled"])
        shot = {"id": "shot08", "heat_phase": "act", "vocal_color": "嗯啊…"}
        payload = resolve_shot_vocal_color(shot, policy=policy)
        self.assertEqual(payload.get("source"), "disabled")
        # explicit opt-in still works
        policy2 = resolve_voice_tracks(
            {
                "heat_scale": "max",
                "voice_tracks": {
                    "enabled": True,
                    "auto_vocal_color": False,
                    "vocal_color_gain": 0.6,
                },
            }
        )
        payload2 = resolve_shot_vocal_color(shot, policy=policy2)
        self.assertEqual(payload2["text"], "嗯啊…")
        self.assertEqual(payload2["source"], "author")
        self.assertGreater(payload2["gain"], 0)

    def test_apply_default_no_auto_color(self) -> None:
        spec = {
            "title": "t",
            "heat_scale": "max",
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "heat_phase": "act",
                            "tone_tags": ["breathy"],
                            "sound_cues": ["breath"],
                        }
                    ]
                }
            ],
        }
        summary = apply_voice_tracks_to_spec(spec, seed=3)
        self.assertEqual(summary["shots_with_color"], 0)
        shot = spec["scenes"][0]["shots"][0]
        self.assertFalse(shot.get("vocal_color"))
        self.assertEqual(shot.get("tone_tags"), ["breathy"])
        self.assertIn("breath", shot.get("_sfx_kinds_from_cues") or [])

    def test_offset_clamp(self) -> None:
        off = compute_color_offset_sec(offset_sec=-1, plate_sec=6.0, color_dur=1.0, vo_dur=4.0)
        self.assertGreaterEqual(off, 0.0)
        self.assertLessEqual(off, 5.0)

    def test_default_voice_tracks_off(self) -> None:
        policy = resolve_voice_tracks({"heat_scale": "max"})
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["auto_vocal_color"])
        self.assertEqual(float(policy["vocal_color_gain"]), 0.0)


if __name__ == "__main__":
    unittest.main()
