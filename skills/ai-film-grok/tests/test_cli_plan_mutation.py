#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli_plan_mutation import PlanMutationError, run  # noqa: E402


class PlanMutationRouteTests(unittest.TestCase):
    def test_missing_graph_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PlanMutationError) as ctx:
                run(Namespace(plan_action="edit", node="story", set=["goal=x"]), Path(tmp))
            self.assertEqual(ctx.exception.code, "GRAPH_MISSING")

    def test_replan_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "drama-graph.json").write_text('{"schema_version": 2}\n', encoding="utf-8")
            with self.assertRaises(PlanMutationError) as ctx:
                run(Namespace(plan_action="replan", node="story", descendants=False), root)
            self.assertEqual(ctx.exception.code, "DESCENDANTS_CONFIRM_REQUIRED")


if __name__ == "__main__":
    unittest.main()
