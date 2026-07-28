#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "aifilm_grok.py"


class CliSmokeTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    @pytest.mark.slow
    def test_help_and_skill_list(self) -> None:
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        result = self.run_cli("skill", "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIn("image.animate", {item["id"] for item in payload["skills"]})

    def test_comfy_lan_control_help(self) -> None:
        result = self.run_cli("comfy", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("inventory", result.stdout)
        self.assertIn("upload", result.stdout)
        self.assertIn("run-workflow", result.stdout)
        self.assertIn("cancel", result.stdout)
        self.assertIn("free-memory", result.stdout)


if __name__ == "__main__":
    unittest.main()
