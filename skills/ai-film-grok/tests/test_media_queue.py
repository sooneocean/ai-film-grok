from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_queue import MediaQueue, QueueError  # noqa: E402


def iso(seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class MediaQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "film"
        self.prompt = Path(self.tmp.name) / "prompt.txt"
        self.prompt.write_text("camera slowly pushes in", encoding="utf-8")
        self.frame = Path(self.tmp.name) / "frame.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=red:s=160x90", "-frames:v", "1", str(self.frame)],
            check=True,
            capture_output=True,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def queue(self) -> MediaQueue:
        return MediaQueue(self.root)

    def _approve_pilot(self) -> None:
        receipts = self.root / "receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        (receipts / "pilot-approval.json").write_text(
            json.dumps(
                {
                    "approved": True,
                    "approved_by": "user",
                    "shots": ["shot01", "shot02", "shot03"],
                    "notes": "test pilot",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def add(self, **kwargs) -> dict[str, object]:
        params = dict(
            shot_id="shot01",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
            max_attempts=3,
            allow_without_pilot=True,
        )
        params.update(kwargs)
        return self.queue().add_job(**params)

    def test_add_is_deduplicated_by_prompt_and_input_hashes(self) -> None:
        first = self.add()
        second = self.add()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.queue().state()["jobs"]), 1)
        self.assertIn("prompt_sha256", first)

    def test_generation_unit_budget_blocks_unbounded_queue_growth(self) -> None:
        queue = MediaQueue(self.root, budget_units=1)
        queue.add_job(
            shot_id="shot01",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
            allow_without_pilot=True,
        )
        with self.assertRaises(QueueError):
            queue.add_job(
                shot_id="shot02",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
                allow_without_pilot=True,
            )

    def test_generation_unit_budget_can_be_explicitly_raised(self) -> None:
        queue = MediaQueue(self.root, budget_units=1)
        queue.add_job(
            shot_id="shot01",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
            allow_without_pilot=True,
        )
        queue.set_budget(2)
        queue.add_job(
            shot_id="shot02",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
            allow_without_pilot=True,
        )
        self.assertEqual(queue.metrics()["budget_units"], 2)
        self.assertEqual(queue.metrics()["budget_remaining"], 0)

    def test_only_one_job_can_be_running_and_failure_uses_backoff(self) -> None:
        job = self.add()
        claimed = self.queue().claim(now=iso())
        self.assertEqual(claimed["id"], job["id"])
        with self.assertRaises(QueueError):
            self.queue().claim(now=iso())
        failed = self.queue().fail(
            job["id"],
            claim_token=claimed["claim_token"],
            error="provider timeout",
            reason="other",
            retryable=True,
            now=iso(),
        )
        self.assertIn(failed["status"], {"pending", "failed"})

    def test_pilot_window_allows_three_then_blocks_fourth(self) -> None:
        queue = MediaQueue(self.root, budget_units=20)
        for i in range(1, 4):
            queue.add_job(
                shot_id=f"shot{i:02d}",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
            )
        with self.assertRaisesRegex(QueueError, "pilot"):
            queue.add_job(
                shot_id="shot04",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
            )

    def test_pilot_user_approval_unlocks_bulk(self) -> None:
        queue = MediaQueue(self.root, budget_units=20)
        for i in range(1, 4):
            queue.add_job(
                shot_id=f"shot{i:02d}",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
            )
        self._approve_pilot()
        job = queue.add_job(
            shot_id="shot04",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
        )
        self.assertEqual(job["shot_id"], "shot04")

    def test_agent_self_approve_does_not_unlock(self) -> None:
        receipts = self.root / "receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        (receipts / "pilot-approval.json").write_text(
            json.dumps({"approved": True, "approved_by": "agent", "shots": ["shot01"]}),
            encoding="utf-8",
        )
        queue = MediaQueue(self.root, budget_units=20)
        for i in range(1, 4):
            queue.add_job(
                shot_id=f"shot{i:02d}",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
            )
        with self.assertRaisesRegex(QueueError, "pilot"):
            queue.add_job(
                shot_id="shot04",
                operation="image_to_video",
                prompt_file=self.prompt,
                inputs=[self.frame],
            )


if __name__ == "__main__":
    unittest.main()
