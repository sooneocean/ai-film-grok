#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
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

    def test_received_flag_uses_canonical_root_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = root / "receipts" / "story-reception.json"
            receipt.parent.mkdir(parents=True)
            raw_text = "雨夜，兩人被困在車站。"
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "story-reception",
                        "source": {
                            "source_ref": "story.txt",
                            "raw_text": raw_text,
                            "sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
                            "language": "zh-TW",
                        },
                        "treatment": {
                            "title": "雨站",
                            "logline": "雨夜中的選擇。",
                            "planning_text": "雨夜，兩人被困在車站，必須做出選擇。",
                            "provenance": {
                                "title": "creative_suggestion",
                                "logline": "creative_suggestion",
                                "planning_text": "source_supported",
                            },
                        },
                        "fidelity": {
                            "immutable_facts": [],
                            "protected_dialogue": [],
                            "explicit_constraints": [],
                            "unknowns": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            report, code = run(
                Namespace(
                    file=None,
                    text=None,
                    received=True,
                    received_file=None,
                    title=None,
                    target_duration=480,
                    production_mode="longform",
                    apply_film_spec=False,
                    no_film_spec=True,
                    force=True,
                    no_bible=True,
                    story_mode="narrative",
                ),
                root,
            )
            self.assertEqual(code, 0, report)
            graph = json.loads((root / "drama-graph.json").read_text())
            self.assertEqual(graph["project"]["production_mode"], "longform")

    def test_longform_rejects_short_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(PlanRunError, "480..900"):
            run(
                Namespace(
                    file=None,
                    text="雨夜車站。",
                    received=False,
                    received_file=None,
                    title="雨站",
                    target_duration=90,
                    production_mode="longform",
                    apply_film_spec=False,
                    no_film_spec=True,
                    force=True,
                    no_bible=True,
                    story_mode="narrative",
                ),
                Path(tmp),
            )


if __name__ == "__main__":
    unittest.main()
