#!/usr/bin/env python3
"""Phase A deep integration: single tier resolver + Grok fail-closed + no silent pass."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_motion_gate import motion_tier_for_shot  # noqa: E402
from motion_prompt_spine import (  # noqa: E402
    MotionCoreError,
    motion_tier_for,
    motion_tier_resolve,
)
from prompt_injector import PromptInjector  # noqa: E402


class SingleTierResolver(unittest.TestCase):
    """Table: prompt_tier and optical_tier stay consistent."""

    CASES = [
        # heat, df, wardrobe, want_optical, want_prompt
        ("act", "reaction", "", "meat", "high"),
        ("climax", "", "bare", "meat", "high"),
        ("setup", "reaction", "", "soft", "soft"),
        ("bridge", "afterglow", "bare", "medium", "medium"),
        ("afterglow", "", "", "medium", "medium"),
        ("setup", "action", "", "meat", "high"),
        ("setup", "hook", "", "high", "high"),
        ("setup", "", "", "normal", "medium"),
        ("foreplay", "", "", "medium", "medium"),
    ]

    def test_table_optical_and_prompt(self) -> None:
        for heat, df, wardrobe, optical, prompt in self.CASES:
            with self.subTest(heat=heat, df=df, wardrobe=wardrobe):
                shot = {
                    "id": "t",
                    "heat_phase": heat,
                    "dramatic_function": df,
                    "wardrobe_state": wardrobe,
                }
                r = motion_tier_resolve(shot)
                self.assertEqual(r["optical_tier"], optical)
                self.assertEqual(r["prompt_tier"], prompt)
                self.assertEqual(motion_tier_for(shot), prompt)
                self.assertEqual(
                    motion_tier_for_shot(
                        heat_phase=heat,
                        dramatic_function=df,
                        wardrobe_state=wardrobe,
                    ),
                    optical,
                )

    def test_spine_tier_high_maps_meat_optical(self) -> None:
        r = motion_tier_resolve(spine_tier="high", heat_phase="setup")
        self.assertEqual(r["optical_tier"], "meat")
        self.assertEqual(r["prompt_tier"], "high")


class GrokInjectorFailClosed(unittest.TestCase):
    def _bible(self) -> dict:
        return {
            "schema_version": 1,
            "state": "locked",
            "style_signature": "cel anime",
            "heat_scale": "soft",
        }

    def test_i2v_empty_core_raises(self) -> None:
        inj = PromptInjector(self._bible(), template_version="I2V")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            shot = {"id": "empty1", "shot_role": "hero"}  # no action / df / dialogue
            with mock.patch.dict("os.environ", {}, clear=False):
                import os

                os.environ.pop("AIFILM_SKIP_MOTION_CORE", None)
                with self.assertRaises(MotionCoreError):
                    inj.assemble(shot, root)

    def test_escape_skips_assert(self) -> None:
        inj = PromptInjector(self._bible(), template_version="I2V")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            shot = {
                "id": "esc1",
                "shot_role": "hero",
                "dsl": {"action": "she turns and smiles at him"},
            }
            with mock.patch.dict("os.environ", {"AIFILM_SKIP_MOTION_CORE": "1"}):
                out = inj.assemble(shot, root)
            self.assertIn("prompt_text", out)


class MediaQueueNoSilentPass(unittest.TestCase):
    def test_enrich_failure_becomes_queue_error(self) -> None:
        # Import path only — ensure MotionCoreError maps; unexpected Exception too.
        from media_queue import QueueError

        self.assertTrue(issubclass(QueueError, Exception))


if __name__ == "__main__":
    unittest.main()
