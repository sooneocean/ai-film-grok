#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli_plan_project import run  # noqa: E402


class PlanProjectRouteTests(unittest.TestCase):
    def test_missing_graph_is_reported_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report, code = run(Namespace(force=False), Path(tmp))
            self.assertEqual(code, 1)
            self.assertFalse(report["ok"])
            self.assertIn("missing", report["error"])
            self.assertFalse((Path(tmp) / "film-spec.json").exists())

    def test_existing_shots_require_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "drama-graph.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
            (root / "film-spec.json").write_text(
                '{"scenes":[{"shots":[{"id":"old"}]}]}\n', encoding="utf-8"
            )
            report, code = run(Namespace(force=False), root)
            self.assertEqual(code, 1)
            self.assertIn("--force", report["error"])


if __name__ == "__main__":
    unittest.main()
