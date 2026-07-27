from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from motion_evidence import MotionEvidenceError, build_motion_generation_evidence  # noqa: E402


def test_dry_run_is_explicitly_not_delivery_evidence(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"preview")

    receipt = build_motion_generation_evidence(
        tmp_path,
        shot_id="s001",
        clip=clip,
        source_endpoint="image_to_video",
        queue_job_id=None,
        dry_run=True,
    )

    assert receipt["delivery_eligible"] is False
    assert receipt["status"] == "dry-run"


def test_provider_evidence_rejects_missing_or_mismatched_queue_receipt(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"provider output")

    with pytest.raises(MotionEvidenceError, match="queue-job-id"):
        build_motion_generation_evidence(
            tmp_path,
            shot_id="s001",
            clip=clip,
            source_endpoint="image_to_video",
            queue_job_id=None,
        )
