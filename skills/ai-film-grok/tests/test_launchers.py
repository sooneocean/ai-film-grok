from __future__ import annotations

import subprocess
import unittest
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_runtime_resolver_selects_python_311_or_newer(self) -> None:
        result = subprocess.run(
            [str(ROOT / "scripts" / "runtime-python")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved = Path(result.stdout.strip())
        self.assertTrue(resolved.is_file())
        version = subprocess.run(
            [str(resolved), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertGreaterEqual(tuple(map(int, version.stdout.strip().split("."))), (3, 11))

    def test_runtime_resolver_rejects_explicit_unsupported_python(self) -> None:
        legacy = Path("/usr/bin/python3")
        if not legacy.is_file():
            self.skipTest("no system Python to exercise explicit legacy rejection")
        env = dict(os.environ, AIFILM_PYTHON=str(legacy))
        result = subprocess.run(
            [str(ROOT / "scripts" / "runtime-python")],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode == 0:
            self.skipTest("system Python is already supported")
        self.assertIn("older than Python 3.11", result.stderr)

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
