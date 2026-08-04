from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from motion_evidence import (  # noqa: E402
    MotionEvidenceError,
    build_motion_generation_evidence,
    require_queue_job_for_canonical_project,
)


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


def test_canonical_clip_promotion_requires_a_queue_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import narrative_control

    monkeypatch.setattr(
        narrative_control,
        "control_status",
        lambda _root: {"canonical": True},
    )

    with pytest.raises(MotionEvidenceError, match="queue-job-id"):
        require_queue_job_for_canonical_project(tmp_path, queue_job_id=None)

    require_queue_job_for_canonical_project(tmp_path, queue_job_id="job-1")


def test_register_clip_calls_the_canonical_queue_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aifilm_grok
    import narrative_control

    monkeypatch.setattr(
        narrative_control,
        "control_status",
        lambda _root: {"canonical": True},
    )
    # Dummy path must exist so true-video path check does not shadow queue-job gate
    clip = tmp_path / "take.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    args = Namespace(
        root=str(tmp_path),
        source=str(clip),
        source_endpoint="image_to_video",
        status="approved",
        shot_id="s01",
        queue_job_id=None,
    )

    with pytest.raises(aifilm_grok.FilmError, match="queue-job-id"):
        aifilm_grok.cmd_register_clip(args)
