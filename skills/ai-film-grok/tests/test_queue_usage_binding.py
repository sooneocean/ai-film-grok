"""U13 tests: retry audit trail and queue/provider usage binding."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generation_usage import finish_generation, start_generation
from media_queue import MediaQueue, QueueError
from media_queue import main as queue_main


def _iso(offset: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=offset)).replace(microsecond=0).isoformat()


def _queue(tmp_path: Path) -> tuple[MediaQueue, Path, Path]:
    root = tmp_path / "film"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("slow push in", encoding="utf-8")
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")
    return MediaQueue(root, budget_units=5), prompt, image


def test_retry_history_records_backoff_and_manual_requeue(tmp_path: Path) -> None:
    queue, prompt, image = _queue(tmp_path)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
    )
    claimed = queue.claim(now=_iso())
    failed = queue.fail(
        job["id"],
        claim_token=claimed["claim_token"],
        error="HTTP 429",
        reason="rate_limit",
        retryable=True,
        now=_iso(),
    )
    assert failed["status"] == "pending"
    assert failed["retry_history"][-1]["reason"] == "rate_limit"
    assert failed["retry_history"][-1]["next_attempt_at"] is not None
    requeued = queue.requeue(job["id"], reason="rate_limit", now=_iso())
    assert len(requeued["retry_history"]) == 2
    assert requeued["retry_history"][-1]["manual"] is True


def test_complete_binds_terminal_generation_usage_to_job(tmp_path: Path) -> None:
    queue, prompt, image = _queue(tmp_path)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
    )
    claimed = queue.claim(now=_iso())
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"video")
    generation_id = start_generation(
        queue.root,
        operation="i2v",
        provider="grok",
        model="grok-imagine-video",
        shot_id="shot01",
        job_id=job["id"],
        generation_id="gen-job-1",
    )
    finish_generation(
        queue.root,
        generation_id,
        status="succeeded",
        measurement="provider_exact",
        provider_request_id="req-1",
        usage={"cost_in_usd_ticks": 250},
        output=output,
    )
    with patch("media_queue.analyze_media", return_value={"ok": True, "motion": {"ok": True}}):
        result = queue.complete(
            job["id"],
            claim_token=claimed["claim_token"],
            output=output,
            endpoint="image_to_video",
            generation_id=generation_id,
        )
    binding = result["receipt"]["generation_usage"]
    assert binding["generation_id"] == "gen-job-1"
    assert binding["cost_in_usd_ticks"] == 250


def test_complete_rejects_usage_receipt_for_other_job(tmp_path: Path) -> None:
    queue, prompt, image = _queue(tmp_path)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
    )
    claimed = queue.claim(now=_iso())
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"video")
    generation_id = start_generation(
        queue.root,
        operation="i2v",
        provider="grok",
        job_id="different-job",
        generation_id="gen-other-job",
    )
    finish_generation(queue.root, generation_id, status="succeeded", output=output)
    with patch("media_queue.analyze_media", return_value={"ok": True, "motion": {"ok": True}}):
        try:
            queue.complete(
                job["id"],
                claim_token=claimed["claim_token"],
                output=output,
                endpoint="image_to_video",
                generation_id=generation_id,
            )
        except QueueError as exc:
            assert "belongs to job" in str(exc)
        else:
            raise AssertionError("mismatched generation usage was accepted")


def test_complete_rejects_usage_receipt_from_different_generation_contract(
    tmp_path: Path,
) -> None:
    queue, prompt, image = _queue(tmp_path)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
        generation_contract={
            "provider": "grok",
            "model": "grok-imagine-video",
            "parameters": {"duration": 6},
            "version": "1",
        },
    )
    claimed = queue.claim(now=_iso())
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"video")
    generation_id = start_generation(
        queue.root,
        operation="i2v",
        provider="grok",
        model="grok-imagine-video",
        job_id=job["id"],
        cache_key="0" * 64,
    )
    finish_generation(queue.root, generation_id, status="succeeded", output=output)
    with patch("media_queue.analyze_media", return_value={"ok": True, "motion": {"ok": True}}):
        try:
            queue.complete(
                job["id"],
                claim_token=claimed["claim_token"],
                output=output,
                endpoint="image_to_video",
                generation_id=generation_id,
            )
        except QueueError as exc:
            assert "contract does not match" in str(exc)
        else:
            raise AssertionError("mismatched generation contract was accepted")


def test_complete_receipt_carries_generation_contract_identity(tmp_path: Path) -> None:
    queue, prompt, image = _queue(tmp_path)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
        generation_contract={"provider": "grok", "model": "video-1", "version": "1"},
    )
    claimed = queue.claim(now=_iso())
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"video")
    generation_id = start_generation(
        queue.root,
        operation="i2v",
        provider="grok",
        model="video-1",
        job_id=job["id"],
        cache_key=job["cache_key"],
    )
    finish_generation(queue.root, generation_id, status="succeeded", output=output)
    with patch("media_queue.analyze_media", return_value={"ok": True, "motion": {"ok": True}}):
        result = queue.complete(
            job["id"],
            claim_token=claimed["claim_token"],
            output=output,
            endpoint="image_to_video",
            generation_id=generation_id,
        )
    binding = result["receipt"]["generation_usage"]
    assert binding["cache_key"] == job["cache_key"]


def test_generation_contract_changes_queue_identity(tmp_path: Path) -> None:
    queue, prompt, image = _queue(tmp_path)
    first = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
        generation_contract={
            "provider": "grok",
            "model": "grok-imagine-video",
            "parameters": {"duration": 5},
            "version": "1",
        },
    )
    second = queue.add_job(
        shot_id="shot01",
        operation="image_to_video",
        prompt_file=prompt,
        inputs=[image],
        allow_without_pilot=True,
        generation_contract={
            "provider": "grok",
            "model": "grok-imagine-video",
            "parameters": {"duration": 6},
            "version": "1",
        },
    )
    assert first["id"] != second["id"]
    assert first["cache_key"] != second["cache_key"]


def test_queue_cli_accepts_generation_contract(tmp_path: Path, capsys) -> None:
    root = tmp_path / "film"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("slow push in", encoding="utf-8")
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")
    assert (
        queue_main(
            [
                "add",
                "--root",
                str(root),
                "--shot-id",
                "shot01",
                "--operation",
                "image_to_video",
                "--prompt-file",
                str(prompt),
                "--input",
                str(image),
                "--allow-without-pilot",
                "--provider",
                "grok",
                "--model",
                "grok-imagine-video",
                "--parameters-json",
                '{"duration":5}',
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["cache_key"]
    assert output["result"]["generation_contract"]["model"] == "grok-imagine-video"
