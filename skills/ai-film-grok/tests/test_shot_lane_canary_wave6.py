"""Wave 6 · synthetic shot-lane canary (8 lanes, no GPU)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ShotLaneCanaryWave6(unittest.TestCase):
    def test_eight_lane_coverage(self) -> None:
        from continue_handoff import resolve_continue_handoff
        from dialogue_speaker_frame_gate import (
            lint_dialogue_prompt_speech,
            lint_dialogue_still_recipe,
        )
        from h3_mode import resolve_h3_mode
        from shot_lane import resolve_film_shot_lanes
        from util import write_json

        root = Path(tempfile.mkdtemp(prefix="shot-lane-canary-"))
        shots = [
            {
                "id": "s_setup",
                "shot_role": "hero",
                "heat_phase": "setup",
                "wardrobe_state": "clothed",
                "dramatic_function": "setup",
                "shot_size": "ms",
            },
            {
                "id": "s_dlg_safe",
                "shot_role": "hero",
                "heat_phase": "setup",
                "wardrobe_state": "clothed",
                "screen_mode": "on_camera",
                "shot_size": "mcu",
                "speaker": "heroine",
                "audio_cues": [
                    {
                        "spoken_text": "你好",
                        "screen_mode": "on_camera",
                        "speaker": "heroine",
                    }
                ],
            },
            {
                "id": "s_dlg_rest",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "screen_mode": "on_camera",
                "shot_size": "cu",
                "speaker": "heroine",
                "audio_cues": [
                    {
                        "spoken_text": "别停",
                        "screen_mode": "on_camera",
                        "speaker": "heroine",
                    }
                ],
            },
            {
                "id": "s_meat",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "dramatic_function": "action",
                "shot_size": "ms",
            },
            {
                "id": "s_insert",
                "shot_role": "insert",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "shot_size": "l4",
            },
            {
                "id": "s_env",
                "dramatic_function": "establishing",
                "heat_phase": "setup",
            },
            {
                "id": "s_cont",
                "parent_shot_id": "s_meat",
                "dsl": {"chain_mode": "continue"},
                "heat_phase": "act",
                "wardrobe_state": "bare",
            },
            {
                "id": "s_poison",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
            },
        ]
        write_json(
            root / "film-spec.json",
            {
                "title": "shot-lane-canary",
                "genre": "adult",
                "heat_scale": "max",
                "vo_mode": "dialogue_drama",
                "scenes": [{"id": "sc01", "shots": shots}],
            },
        )
        write_json(
            root / "manifest.json",
            {
                "stills": {
                    "s_poison": {
                        "status": "approved",
                        "anatomy_safe": False,
                        "path": "stills/p.png",
                    },
                    "s_meat": {
                        "status": "approved",
                        "anatomy_safe": True,
                        "path": "stills/m.png",
                    },
                    "s_dlg_rest": {
                        "status": "approved",
                        "anatomy_safe": True,
                        "path": "stills/d.png",
                    },
                },
                "clips": {},
            },
        )
        hd = root / "receipts" / "continue-handoff"
        hd.mkdir(parents=True)
        end = hd / "s_meat_end.png"
        end.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
        write_json(
            hd / "s_meat.json",
            {
                "ok": False,
                "safe_for_continue": False,
                "end_frame": str(end),
                "block_codes": ["ENDFRAME_REDRESS_RISK"],
                "shot_id": "s_meat",
            },
        )

        rep = resolve_film_shot_lanes(root)
        by = {r["shot_id"]: r for r in rep["shots"]}
        self.assertEqual(by["s_setup"]["lane"], "setup")
        self.assertEqual(by["s_dlg_safe"]["lane"], "dialogue_safe")
        self.assertEqual(by["s_dlg_rest"]["lane"], "dialogue_restricted")
        self.assertEqual(by["s_meat"]["lane"], "meat")
        self.assertEqual(by["s_insert"]["lane"], "insert")
        self.assertEqual(by["s_env"]["lane"], "env")
        self.assertEqual(by["s_env"]["h3_mode"], "t2v")
        self.assertEqual(by["s_cont"]["lane"], "continue")
        self.assertEqual(by["s_poison"]["lane"], "poison_blocked")
        self.assertFalse(by["s_poison"]["i2v_allowed"])
        self.assertIn(
            "INSERT_NEEDS_DETAIL_STILL", by["s_insert"].get("blocked_by") or []
        )

        crep = resolve_continue_handoff(root, "s_cont")
        self.assertFalse(crep.get("ok"))
        self.assertIn("ENDFRAME_REDRESS_RISK", crep.get("block_codes") or [])

        self.assertTrue(lint_dialogue_still_recipe(shots[1]).get("ok"))
        self.assertFalse(
            lint_dialogue_prompt_speech("soft portrait, no speech", shots[2]).get("ok")
        )
        self.assertEqual(
            resolve_h3_mode(shots[5], has_still=False).get("mode"), "t2v"
        )

        # expected 8 lane kinds present
        counts = rep.get("lane_counts") or {}
        for lane in (
            "setup",
            "dialogue_safe",
            "dialogue_restricted",
            "meat",
            "insert",
            "env",
            "continue",
            "poison_blocked",
        ):
            self.assertGreaterEqual(int(counts.get(lane) or 0), 1, msg=lane)


if __name__ == "__main__":
    unittest.main()
