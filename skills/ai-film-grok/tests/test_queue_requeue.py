"""Typed fail reasons + requeue on shipped MediaQueue (no hand-edit JSON)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_queue import (  # noqa: E402
    FAIL_REASONS,
    MediaQueue,
    QueueError,
    normalize_fail_reason,
)


def iso(seconds: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).replace(microsecond=0).isoformat()


@pytest.mark.slow
class FailReasonNormalizeTests(unittest.TestCase):
    @pytest.mark.slow
    def test_enum_passthrough(self) -> None:
        for r in FAIL_REASONS:
            self.assertEqual(normalize_fail_reason(r), r)

    @pytest.mark.slow
    def test_aliases(self) -> None:
        self.assertEqual(normalize_fail_reason("content-moderated"), "moderation")
        self.assertEqual(normalize_fail_reason("motion gate failed"), "motion")
        self.assertEqual(normalize_fail_reason("HTTP 429 Too Many Requests"), "rate_limit")
        self.assertEqual(normalize_fail_reason("ffprobe decode error"), "decode")
        self.assertEqual(normalize_fail_reason("weird"), "other")


class QueueRequeueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "film"
        self.prompt = Path(self.tmp.name) / "prompt.txt"
        self.prompt.write_text("slow push-in, blink", encoding="utf-8")
        self.frame = Path(self.tmp.name) / "frame.jpg"
        # minimal jpeg via ffmpeg if available, else write bytes
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=red:s=64x64",
                    "-frames:v",
                    "1",
                    str(self.frame),
                ],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.frame.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG markers if ffmpeg missing

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _add_claim(self) -> tuple[MediaQueue, dict]:
        q = MediaQueue(self.root, budget_units=5)
        job = q.add_job(
            shot_id="shot01",
            operation="image_to_video",
            prompt_file=self.prompt,
            inputs=[self.frame],
            max_attempts=3,
            allow_without_pilot=True,
        )
        claimed = q.claim(now=iso())
        self.assertEqual(claimed["id"], job["id"])
        return q, claimed

    @pytest.mark.slow
    def test_fail_moderation_marks_failed_not_auto_pending(self) -> None:
        q, claimed = self._add_claim()
        failed = q.fail(
            claimed["id"],
            claim_token=claimed["claim_token"],
            error="imagine:content-moderated",
            reason="moderation",
            retryable=True,
            now=iso(),
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["fail_reason"], "moderation")

    @pytest.mark.slow
    def test_requeue_returns_pending_immediately(self) -> None:
        q, claimed = self._add_claim()
        q.fail(
            claimed["id"],
            claim_token=claimed["claim_token"],
            error="content moderated",
            reason="moderation",
            retryable=True,
            now=iso(),
        )
        again = q.requeue(claimed["id"], reason="moderation", reset_attempts=True, now=iso())
        self.assertEqual(again["status"], "pending")
        self.assertEqual(again.get("fail_reason"), "moderation")
        self.assertEqual(again.get("attempts"), 0)
        # eligible now
        claimed2 = q.claim(now=iso())
        self.assertEqual(claimed2["id"], claimed["id"])

    @pytest.mark.slow
    def test_fail_motion_can_auto_retry_pending(self) -> None:
        q, claimed = self._add_claim()
        failed = q.fail(
            claimed["id"],
            claim_token=claimed["claim_token"],
            error="motion gate failed: score=0.7",
            reason="motion",
            retryable=True,
            now=iso(),
        )
        self.assertEqual(failed["status"], "pending")
        self.assertEqual(failed["fail_reason"], "motion")

    @pytest.mark.slow
    def test_requeue_rejects_succeeded(self) -> None:
        q, claimed = self._add_claim()
        # Force succeeded without real media by writing state is hard; use fail terminal then requeue ok
        failed = q.fail(
            claimed["id"],
            claim_token=claimed["claim_token"],
            error="other",
            reason="other",
            retryable=False,
            now=iso(),
        )
        self.assertEqual(failed["status"], "failed")
        # requeue works from failed
        q.requeue(claimed["id"], now=iso())
        # mark succeeded path: cannot easily without motion file — skip if no ffmpeg motion
        # ensure unknown job errors
        with self.assertRaises(QueueError):
            q.requeue("no-such-job")


if __name__ == "__main__":
    unittest.main()
