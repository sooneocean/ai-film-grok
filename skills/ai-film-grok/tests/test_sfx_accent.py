"""sfx_accent overlay + auto inject from dramatic_function."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from sound_plan import (  # noqa: E402
    apply_sfx_accents_to_samples,
    expand_sound_events,
    inject_auto_sfx_if_empty,
    sfx_clip_for_kind,
    suggest_auto_sfx_events,
    validate_sound_plan,
)


class SfxAccentTests(unittest.TestCase):
    def test_sfx_clip_kinds_nonempty(self) -> None:
        for kind in ("heartbeat", "whoosh", "chime", "impact", "breath", "generic"):
            clip = sfx_clip_for_kind(kind, amp=0.2)
            self.assertGreater(len(clip), 100, msg=kind)
            self.assertGreater(float(np.max(np.abs(clip))), 1e-4, msg=kind)

    def test_overlay_raises_energy_in_window(self) -> None:
        sr = 44100
        bed = np.zeros(sr * 3, dtype=np.float64)  # 3s silence
        events = [
            {
                "type": "sfx_accent",
                "kind": "whoosh",
                "at_sec": 1.0,
                "applied": True,
            }
        ]
        out = apply_sfx_accents_to_samples(bed, sr=sr, events=events, level=0.8)
        # window around 1.0–1.4s should have energy
        a, b = int(1.0 * sr), int(1.4 * sr)
        self.assertGreater(float(np.max(np.abs(out[a:b]))), 0.01)
        self.assertTrue(events[0].get("overlay_applied"))

    def test_auto_sfx_from_beats(self) -> None:
        shots = [
            {"id": "shot01", "dramatic_function": "hook"},
            {"id": "shot02", "dramatic_function": "sensory"},
            {"id": "shot03", "dramatic_function": "action"},
        ]
        evs = suggest_auto_sfx_events(shots)
        self.assertEqual(len(evs), 3)
        kinds = {e["shot_id"]: e["kind"] for e in evs}
        self.assertEqual(kinds["shot01"], "whoosh")
        self.assertEqual(kinds["shot02"], "heartbeat")
        self.assertEqual(kinds["shot03"], "impact")

    def test_inject_skips_when_author_has_accents(self) -> None:
        plan = {
            "mood": "rnb",
            "bed": True,
            "events": [{"type": "sfx_accent", "shot_id": "shot01", "kind": "chime"}],
        }
        out = inject_auto_sfx_if_empty(plan, [{"id": "shot01", "dramatic_function": "hook"}])
        assert out is not None
        self.assertEqual(len(out["events"]), 1)
        self.assertEqual(out["events"][0]["kind"], "chime")

    def test_inject_when_empty(self) -> None:
        plan = {"mood": "rnb", "bed": True, "events": [], "auto_sfx": True}
        out = inject_auto_sfx_if_empty(
            plan,
            [
                {"id": "s1", "dramatic_function": "hook"},
                {"id": "s2", "dramatic_function": "reaction"},
            ],
        )
        assert out is not None
        self.assertGreaterEqual(len(out["events"]), 2)
        expanded = expand_sound_events(out, shot_starts={"s1": 1.5, "s2": 7.5}, total_duration=20.0)
        accents = [e for e in expanded["applied_events"] if e["type"] == "sfx_accent"]
        self.assertEqual(len(accents), 2)
        # whoosh at shot start; reaction chime has offset
        self.assertAlmostEqual(accents[0]["at_sec"], 1.5, places=2)
        self.assertGreater(accents[1]["at_sec"], 7.5)

    def test_auto_sfx_false_skips(self) -> None:
        plan = {"mood": "rnb", "bed": True, "events": [], "auto_sfx": False}
        out = inject_auto_sfx_if_empty(plan, [{"id": "s1", "dramatic_function": "hook"}])
        assert out is not None
        self.assertEqual(out["events"], [])

    def test_unspecified_auto_sfx_is_off(self) -> None:
        plan = validate_sound_plan({"mood": "rnb", "events": []})
        assert plan is not None
        self.assertFalse(plan["auto_sfx"])
        out = inject_auto_sfx_if_empty(plan, [{"id": "s1", "dramatic_function": "action"}])
        assert out is not None
        self.assertEqual(out["events"], [])

    def test_explicit_auto_sfx_remains_an_opt_in(self) -> None:
        plan = validate_sound_plan({"mood": "rnb", "events": [], "auto_sfx": True})
        assert plan is not None
        self.assertTrue(plan["auto_sfx"])
        out = inject_auto_sfx_if_empty(plan, [{"id": "s1", "dramatic_function": "action"}])
        assert out is not None
        self.assertEqual(len(out["events"]), 1)


if __name__ == "__main__":
    unittest.main()
