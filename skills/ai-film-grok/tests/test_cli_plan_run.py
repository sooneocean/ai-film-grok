#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from cli_plan_run import PlanRunError, run  # noqa: E402


class PlanRunRouteTests(unittest.TestCase):
    def test_missing_source_fails_before_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(PlanRunError):
            run(Namespace(file="/not/a/real/story.txt", text=None), Path(tmp))

    def test_one_liner_remains_authoring_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report, code = run(
                Namespace(
                    file=None,
                    text="雨夜车站，陌生人递来一把带血的伞。",
                    title="血伞",
                    target_duration=45,
                    apply_film_spec=True,
                    no_film_spec=False,
                    force=True,
                    no_bible=False,
                ),
                Path(tmp),
            )
            self.assertEqual(code, 0, report)
            self.assertTrue(report.get("authoring_questions"))
            self.assertFalse(report.get("ready_for_projection"))


if __name__ == "__main__":
    unittest.main()
