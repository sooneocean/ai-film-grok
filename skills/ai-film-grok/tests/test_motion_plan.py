from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from motion_plan import build_motion_plan  # noqa: E402


class MotionPlanTests(unittest.TestCase):
    def test_panel_animation_plan_is_explicitly_not_character_motion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        # Explicit panel package — Ken Burns only legal when panel
                        "production_mode": "panel",
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "shot01",
                                        "duration_sec": 4,
                                        "dsl": {"motion": "push in"},
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            plan = build_motion_plan(root, "shot01")
            self.assertEqual(plan["production_mode"], "panel-animation")
            self.assertEqual(plan["operation"], "push_in")
            self.assertFalse(plan["human_motion_claim"])
            self.assertTrue(Path(plan["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
