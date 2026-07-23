"""Unit tests for Plate 4: Predictive Media Queue & Canary Auto-Select System.

Verifies:
1. media_queue.py add_canary_pair enqueueing primary and canary jobs.
2. media_queue.py job attributes (is_canary, canary_group_id, seed_offset).
3. caption_frame_audit.py select_best_canary_candidate selection logic.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from caption_frame_audit import select_best_canary_candidate  # noqa: E402
from media_queue import MediaQueue  # noqa: E402


class PredictiveMediaQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.prompt_file = self.root / "prompt.txt"
        self.prompt_file.write_text("Test prompt content", encoding="utf-8")
        self.input_file = self.root / "input.jpg"
        self.input_file.write_bytes(b"dummy image data")

        self.queue = MediaQueue(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_canary_pair(self) -> None:
        primary, canary = self.queue.add_canary_pair(
            shot_id="shot_01",
            operation="image_gen",
            prompt_file=self.prompt_file,
            inputs=[self.input_file],
            allow_without_pilot=True,
            seed_offset=101,
        )

        self.assertFalse(primary["is_canary"])
        self.assertTrue(canary["is_canary"])
        self.assertEqual(canary["seed_offset"], 101)
        self.assertEqual(primary["canary_group_id"], canary["canary_group_id"])

    def test_select_best_canary_candidate(self) -> None:
        candidates = [
            {"id": "c1", "status": "failed", "qa_score": 0.0, "is_canary": False},
            {"id": "c2", "status": "succeeded", "qa_score": 85.0, "is_canary": True},
        ]
        winner = select_best_canary_candidate(candidates)

        self.assertEqual(winner["id"], "c2")
        self.assertTrue(winner["is_canary"])


if __name__ == "__main__":
    unittest.main()
