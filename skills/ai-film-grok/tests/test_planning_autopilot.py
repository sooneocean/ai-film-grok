from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from planning_autopilot import (  # noqa: E402
    answer_transaction,
    apply_authoring_answers,
    authoring_questionnaire,
)
from story_plan import run_plan  # noqa: E402


class PlanningAutopilotTests(unittest.TestCase):
    def test_answer_transaction_is_stable_for_equivalent_object_key_order(self) -> None:
        first = [{"node_ref": "story", "field": "stakes", "value": "失去工作"}]
        second = [{"value": "失去工作", "field": "stakes", "node_ref": "story"}]
        self.assertEqual(answer_transaction(first), answer_transaction(second))

    def test_answer_transaction_changes_when_answer_changes(self) -> None:
        first = [{"node_ref": "story", "field": "stakes", "value": "失去工作"}]
        second = [{"node_ref": "story", "field": "stakes", "value": "失去孩子"}]
        self.assertNotEqual(
            answer_transaction(first)["transaction_id"],
            answer_transaction(second)["transaction_id"],
        )

    def test_mismatched_transaction_is_rejected_before_graph_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，乘客拿出一張照片。", apply_film_spec=False)
            graph_path = root / "drama-graph.json"
            original = graph_path.read_text(encoding="utf-8")
            question = authoring_questionnaire(json.loads(original))[0]
            answer = [
                {
                    "node_ref": question["node_ref"],
                    "field": question["field"],
                    "value": "导演补写",
                }
            ]
            with self.assertRaisesRegex(ValueError, "transaction id"):
                apply_authoring_answers(
                    root, answer, expected_transaction_id="planning-answer-not-this-batch"
                )
            self.assertEqual(graph_path.read_text(encoding="utf-8"), original)
