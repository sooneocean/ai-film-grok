"""Unit tests for Plate 10: 180-Degree Line & Spatial Eyeline Gate System.

Verifies:
1. continuity.py CODE_AXIS_JUMP detection for 180-degree camera axis crossing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity import CODE_AXIS_JUMP, lint_continuity  # noqa: E402


class AxisJumpGateTests(unittest.TestCase):
    def test_axis_jump_lint(self) -> None:
        shots = [
            {"id": "shot01", "camera_axis": "over_right_shoulder"},
            {"id": "shot02", "camera_axis": "over_left_shoulder"},
        ]
        res = lint_continuity(shots)

        self.assertIn(CODE_AXIS_JUMP, res["codes"])

    def test_aligned_axis_passes_lint(self) -> None:
        shots = [
            {"id": "shot01", "camera_axis": "over_right_shoulder"},
            {"id": "shot02", "camera_axis": "center_eye_level"},
            {"id": "shot03", "camera_axis": "over_left_shoulder"},
        ]
        res = lint_continuity(shots)

        self.assertNotIn(CODE_AXIS_JUMP, res["codes"])


if __name__ == "__main__":
    unittest.main()
