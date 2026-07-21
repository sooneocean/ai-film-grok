from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_test_skill_help_is_informational_and_does_not_run_tests(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "test-skill"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage: test-skill", result.stdout)
        self.assertNotIn("Ran ", result.stderr)


if __name__ == "__main__":
    unittest.main()
