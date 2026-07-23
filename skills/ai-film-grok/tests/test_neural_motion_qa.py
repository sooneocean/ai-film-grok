"""Unit tests for Plate 7: Neural Motion & Anatomical QA Audit System.

Verifies:
1. media_qa.py audit_motion_health detecting static_motion (freeze-frame).
2. media_qa.py audit_motion_health detecting motion_glitch (tearing).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_qa import (  # noqa: E402
    FAIL_REASON_MOTION_GLITCH,
    FAIL_REASON_STATIC_MOTION,
    audit_motion_health,
)


class NeuralMotionQATests(unittest.TestCase):
    def test_audit_motion_health_pass(self) -> None:
        res = audit_motion_health("/tmp/clip.mp4", motion_score=5.0, motion_std=12.0)
        self.assertTrue(res["ok"])
        self.assertIsNone(res["reason"])

    def test_audit_motion_health_static_freeze_frame(self) -> None:
        res = audit_motion_health("/tmp/clip.mp4", motion_score=0.1, motion_std=0.01)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], FAIL_REASON_STATIC_MOTION)

    def test_audit_motion_health_glitch_tearing(self) -> None:
        res = audit_motion_health("/tmp/clip.mp4", motion_score=15.0, motion_std=95.0)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], FAIL_REASON_MOTION_GLITCH)


if __name__ == "__main__":
    unittest.main()
