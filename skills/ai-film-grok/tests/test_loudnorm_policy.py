"""Phase G: loudnorm auto/on/off policy + should_apply."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from sound_plan import (  # noqa: E402
    SoundPlanError,
    resolve_loudnorm,
    should_apply_loudnorm,
)


class LoudnormPolicyTests(unittest.TestCase):
    def test_default_auto_target(self) -> None:
        p = resolve_loudnorm(None)
        self.assertEqual(p["mode"], "auto")
        self.assertEqual(p["target_lufs"], -16.0)

    def test_plan_and_cli(self) -> None:
        p = resolve_loudnorm(
            {"loudnorm": "on", "target_lufs": -15},
            mode=None,
            target_lufs=None,
        )
        self.assertEqual(p["mode"], "on")
        self.assertEqual(p["target_lufs"], -15.0)
        p2 = resolve_loudnorm({"loudnorm": "off"}, mode="auto", target_lufs=-17)
        # CLI mode wins when provided
        self.assertEqual(p2["mode"], "auto")
        self.assertEqual(p2["target_lufs"], -17.0)

    def test_bool_aliases(self) -> None:
        self.assertEqual(resolve_loudnorm({"loudnorm": True})["mode"], "on")
        self.assertEqual(resolve_loudnorm({"loudnorm": False})["mode"], "off")

    def test_invalid_mode(self) -> None:
        with self.assertRaises(SoundPlanError):
            resolve_loudnorm(None, mode="maybe")

    def test_should_apply_auto_bands(self) -> None:
        pol = resolve_loudnorm(None, mode="auto")
        self.assertFalse(should_apply_loudnorm(pol, -16.0)[0])
        self.assertTrue(should_apply_loudnorm(pol, -10.0)[0])  # too loud
        self.assertTrue(should_apply_loudnorm(pol, -24.0)[0])  # too quiet
        self.assertFalse(should_apply_loudnorm(pol, None)[0])

    def test_force_and_off(self) -> None:
        on = resolve_loudnorm(None, mode="on")
        off = resolve_loudnorm(None, mode="off")
        self.assertTrue(should_apply_loudnorm(on, -16.0)[0])
        self.assertFalse(should_apply_loudnorm(off, -10.0)[0])


if __name__ == "__main__":
    unittest.main()
