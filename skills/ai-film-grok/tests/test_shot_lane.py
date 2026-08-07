"""Shot generation lane projection (Wave 0 + poison block)."""

from __future__ import annotations

import unittest
from pathlib import Path

from shot_lane import is_poison_blocked, resolve_film_shot_lanes, resolve_shot_lane
from util import write_json


def _film(tmp: Path, shots: list[dict], *, manifest: dict | None = None) -> Path:
    write_json(
        tmp / "film-spec.json",
        {
            "title": "shot-lane-fixture",
            "genre": "adult",
            "heat_scale": "max",
            "scenes": [{"id": "sc01", "shots": shots}],
        },
    )
    write_json(tmp / "manifest.json", manifest if manifest is not None else {"stills": {}, "clips": {}})
    return tmp


class ShotLaneResolveTests(unittest.TestCase):
    def test_env_lane_t2v(self) -> None:
        r = resolve_shot_lane(
            {"id": "e1", "shot_role": "env", "heat_phase": "setup", "wardrobe_state": "clothed"},
            has_still=False,
            has_last=False,
        )
        self.assertEqual(r["lane"], "env")
        self.assertEqual(r["h3_mode"], "t2v")
        self.assertTrue(r["i2v_allowed"])

    def test_dialogue_safe(self) -> None:
        r = resolve_shot_lane(
            {
                "id": "d1",
                "shot_role": "hero",
                "heat_phase": "setup",
                "wardrobe_state": "clothed",
                "screen_mode": "on_camera",
                "shot_size": "mcu",
                "audio_cues": [{"spoken_text": "你好", "screen_mode": "on_camera"}],
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["lane"], "dialogue_safe")
        self.assertIn("speaker_frame", r["required_gates"])
        self.assertEqual(r["h3_mode"], "i2v")

    def test_dialogue_restricted(self) -> None:
        r = resolve_shot_lane(
            {
                "id": "d2",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "screen_mode": "on_camera",
                "shot_size": "cu",
                "audio_cues": [{"spoken_text": "别停", "screen_mode": "on_camera"}],
            },
            intent={"content_class": "restricted_local", "spoken_text": "别停", "screen_mode": "on_camera"},
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["lane"], "dialogue_restricted")
        self.assertIn("anatomy_safe", r["required_gates"])

    def test_meat_lane(self) -> None:
        r = resolve_shot_lane(
            {
                "id": "m1",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "dramatic_function": "action",
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["lane"], "meat")
        self.assertIn("variety_precheck", r["required_gates"])

    def test_continue_lane(self) -> None:
        r = resolve_shot_lane(
            {
                "id": "c1",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "dsl": {"chain_mode": "continue"},
                "parent_shot_id": "m1",
            },
            has_still=True,
            has_last=True,
        )
        self.assertEqual(r["lane"], "continue")
        self.assertEqual(r["h3_mode"], "flf")

    def test_insert_lane(self) -> None:
        r = resolve_shot_lane(
            {
                "id": "i1",
                "shot_role": "insert",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "shot_size": "l4",
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["lane"], "insert")

    def test_poison_blocks_i2v(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as td:
            root = Path(td)
            _film(
                root,
                [
                    {
                        "id": "p1",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                    }
                ],
                manifest={
                    "stills": {
                        "p1": {
                            "status": "approved",
                            "anatomy_safe": False,
                            "path": "stills/p1.png",
                        }
                    },
                    "clips": {},
                },
            )
            self.assertTrue(is_poison_blocked(root, "p1"))
            r = resolve_shot_lane(
                {
                    "id": "p1",
                    "shot_role": "hero",
                    "heat_phase": "act",
                    "wardrobe_state": "bare",
                },
                root=root,
                has_still=True,
            )
            self.assertEqual(r["lane"], "poison_blocked")
            self.assertFalse(r["i2v_allowed"])
            self.assertIn("POISON_STILL_BLOCKS_I2V", r["blocked_by"])

    def test_film_report_counts(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as td:
            root = Path(td)
            _film(
                root,
                [
                    {
                        "id": "s_setup",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "wardrobe_state": "clothed",
                    },
                    {
                        "id": "s_env",
                        "shot_role": "env",
                        "heat_phase": "setup",
                        "wardrobe_state": "clothed",
                    },
                    {
                        "id": "s_dlg",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "wardrobe_state": "clothed",
                        "screen_mode": "on_camera",
                        "audio_cues": [{"spoken_text": "走", "screen_mode": "on_camera"}],
                    },
                ],
            )
            rep = resolve_film_shot_lanes(root)
            self.assertEqual(rep["shot_count"], 3)
            self.assertIn("env", rep["lane_counts"])
            self.assertIn("dialogue_safe", rep["lane_counts"])
            self.assertIn("setup", rep["lane_counts"])


if __name__ == "__main__":
    unittest.main()
