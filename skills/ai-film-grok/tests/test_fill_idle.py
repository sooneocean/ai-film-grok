"""Fill-Idle queue (h3_fill_idle) — P0 meat before soft; next command."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from h3_fill_idle import build_fill_idle_queue, next_fill_idle_job
from util import write_json


class FillIdleQueueTests(unittest.TestCase):
    def test_meat_is_p0_and_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "fill-idle",
                    "h3": {"enabled": True},
                    "genre": "adult",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "survive"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "soft1",
                                    "shot_role": "hero",
                                    "heat_phase": "setup",
                                    "wardrobe_state": "clothed",
                                    "dramatic_function": "bridge",
                                },
                                {
                                    "id": "meat1",
                                    "shot_role": "hero",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                    "dramatic_function": "action",
                                },
                            ]
                        }
                    ],
                },
            )
            (root / "stills").mkdir()
            (root / "stills" / "soft1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
            (root / "takes" / "soft1").mkdir(parents=True)
            clip = root / "takes" / "soft1" / "grok_soft.mp4"
            clip.write_bytes(b"\x00" * 120_000)
            write_json(
                root / "manifest.json",
                {"clips": {"soft1": {"path": str(clip), "mean": 7.5, "status": "candidate"}}},
            )
            q = build_fill_idle_queue(root, include_challenge=True)
            self.assertTrue(q["ok"])
            meat = next(s for s in q["shots"] if s["shot_id"] == "meat1")
            self.assertTrue(str(meat["priority"]).startswith("P0"))
            self.assertTrue(meat.get("primary_h3"))
            nxt = next_fill_idle_job(root, include_challenge=True)
            self.assertTrue(nxt["ok"])
            self.assertEqual(nxt["next"]["shot_id"], "meat1")
            self.assertIn("h3 run", nxt["command"])


if __name__ == "__main__":
    unittest.main()
