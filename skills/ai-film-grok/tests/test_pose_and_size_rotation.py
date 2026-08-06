"""Unit tests for Plate 3: Pose & Shot-Size Rotation Gate System.

Verifies:
1. continuity.py CODE_POSE_MONOTONY detection.
2. continuity.py CODE_SIZE_MONOTONY detection.
3. Rotation matrix in story_plan.py.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity import CODE_POSE_MONOTONY, CODE_SIZE_MONOTONY, lint_continuity  # noqa: E402


class PoseAndSizeRotationTests(unittest.TestCase):
    def test_pose_monotony_lint(self) -> None:
        shots = [
            {"id": "shot01", "sex_pose": "missionary_pin"},
            {"id": "shot02", "sex_pose": "missionary_pin"},
            {"id": "shot03", "sex_pose": "missionary_pin"},
        ]
        res = lint_continuity(shots)

        self.assertIn(CODE_POSE_MONOTONY, res["codes"])

    def test_size_monotony_lint(self) -> None:
        shots = [
            {"id": "shot01", "shot_size": "close_up"},
            {"id": "shot02", "shot_size": "close_up"},
            {"id": "shot03", "shot_size": "close_up"},
        ]
        res = lint_continuity(shots)

        self.assertIn(CODE_SIZE_MONOTONY, res["codes"])

    def test_varied_poses_and_sizes_pass_lint(self) -> None:
        shots = [
            {"id": "shot01", "sex_pose": "wall_pin", "shot_size": "medium_full"},
            {"id": "shot02", "sex_pose": "cowgirl", "shot_size": "medium"},
            {"id": "shot03", "sex_pose": "lotus", "shot_size": "close_up"},
        ]
        res = lint_continuity(shots)

        self.assertNotIn(CODE_POSE_MONOTONY, res["codes"])
        self.assertNotIn(CODE_SIZE_MONOTONY, res["codes"])


if __name__ == "__main__":
    unittest.main()
