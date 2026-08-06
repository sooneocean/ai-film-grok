"""Fill-Idle run-next dry-run + pk-ledger advisory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from h3_fill_idle import (
    _stage_for_fill_idle_job,
    append_pk_ledger,
    load_pk_ledger,
    run_next_fill_idle,
)
from util import write_json


class RunNextLedgerTests(unittest.TestCase):
    def test_stage_pilot_for_p2_challenge(self) -> None:
        self.assertEqual(
            _stage_for_fill_idle_job({"priority": "P2", "lane": "challenge_grok"}),
            "pilot",
        )
        self.assertEqual(
            _stage_for_fill_idle_job({"priority": "P0a", "lane": "primary_h3"}),
            "production",
        )
        self.assertEqual(
            _stage_for_fill_idle_job({"priority": "P1", "lane": "challenge_weak"}),
            "production",
        )

    def test_run_next_dry_run_and_capacity_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "rn",
                    "h3": {"enabled": True},
                    "genre": "adult",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "meat1",
                                    "shot_role": "hero",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                    "dramatic_function": "action",
                                }
                            ]
                        }
                    ],
                },
            )
            rep = run_next_fill_idle(root, execute=False)
            self.assertTrue(rep["ok"])
            self.assertEqual(rep.get("skipped_reason"), "dry_run_pass_execute")
            self.assertIn("meat1", str(rep.get("next_report")))

            with mock.patch(
                "h3_fill_idle.probe_comfy_capacity_soft",
                return_value={"ok": True, "ready": False, "status": "busy"},
            ):
                skip = run_next_fill_idle(root, execute=True, require_capacity=True)
            self.assertEqual(skip.get("skipped_reason"), "capacity_not_ready")
            self.assertFalse(skip.get("ran"))
            self.assertEqual(skip.get("halt_reason_code"), "RUN_NOT_EXECUTED_CAPACITY")
            self.assertIsNotNone(skip.get("open_ops"))
            self.assertTrue(skip["open_ops"])
            self.assertEqual(skip["open_ops"][0].get("halt_reason_code"), "RUN_NOT_EXECUTED_CAPACITY")
            self.assertEqual(skip["open_ops"][0].get("halt_reason_group"), "capacity")
            self.assertEqual(skip["open_ops"][0].get("reason"), "capacity_not_ready")

    def test_run_next_queue_empty_records_decision_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "rn",
                    "h3": {"enabled": True},
                    "genre": "adult",
                    "heat_scale": "max",
                    "director_intent": {"protagonist_want": "x"},
                    "scenes": [],
                },
            )
            with mock.patch(
                "h3_fill_idle.next_fill_idle_job",
                return_value={"ok": True, "next": None, "pending_count": 0},
            ):
                rep = run_next_fill_idle(root, execute=True, max_jobs=1)
            self.assertEqual(rep.get("skipped_reason"), "queue_empty")
            self.assertEqual(rep.get("halt_reason_code"), "RUN_QUEUE_EMPTY")
            self.assertEqual(rep.get("halt_reason_group"), "queue")
            self.assertTrue(rep.get("open_ops"))
            self.assertEqual(rep["open_ops"][0].get("halt_reason_group"), "queue")
            self.assertIn("request", rep.get("decision_tree", {}))
            self.assertEqual(len(rep.get("decision_trees") or []), 1)
            self.assertIn("skipped_reason", rep.get("decision_trees")[0])

    def test_pk_ledger_append_not_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", {"title": "x", "scenes": []})
            led = append_pk_ledger(
                root,
                shot_id="s1",
                winner_path="/tmp/win.mp4",
                winner_lane="h3",
                mean=22.0,
                note="human preferred r2v energy",
            )
            self.assertTrue(led["ok"])
            self.assertEqual(led["count"], 1)
            self.assertFalse(led["entries"][0]["auto_applied"])
            again = load_pk_ledger(root)
            self.assertEqual(again["count"], 1)
            self.assertIn("never", again.get("policy", "").lower() + again.get("note", "").lower())


if __name__ == "__main__":
    unittest.main()
