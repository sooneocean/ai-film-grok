"""Tests for hash-bound final-render shot checkpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import checkpoint
from checkpoint import CheckpointManager


def _fake_media_evidence(path: Path) -> dict[str, object]:
    return {
        "sha256": checkpoint.sha256_file(path),
        "bytes": path.stat().st_size,
        "duration_sec": 4.0,
        "video": {"width": 720, "height": 1280, "avg_frame_rate": "30/1"},
        "audio_streams": 0,
        "full_decode": True,
    }


def test_checkpoint_roundtrip_and_resume_requires_matching_signature(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(checkpoint, "_media_evidence", _fake_media_evidence)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip-v1")
    output = tmp_path / "work" / "shot01.mp4"
    output.parent.mkdir()
    output.write_bytes(b"rendered")

    manager = CheckpointManager(tmp_path)
    signature = manager.signature(
        clip,
        target=4.0,
        width=720,
        height=1280,
        fps=30,
        lipsync="off",
    )
    manager.mark_done(
        "shot01",
        signature=signature,
        output=output,
        metadata={"target": 4.0, "stretch_plan": {"mode": "trim"}},
    )

    restored = CheckpointManager(tmp_path)
    record = restored.get("shot01", signature)
    assert record is not None
    assert record["metadata"]["target"] == 4.0
    assert restored.get("shot01", "0" * 64) is None
    changed_contract = restored.signature(
        clip,
        target=4.0,
        width=720,
        height=1280,
        fps=30,
        lipsync="off",
        contract={"tts_backend": "edge"},
    )
    assert changed_contract != signature
    assert (
        json.loads((tmp_path / "receipts/checkpoints/final-render.json").read_text())[
            "schema_version"
        ]
        == 2
    )


def test_checkpoint_invalidates_changed_clip_and_clear(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(checkpoint, "_media_evidence", _fake_media_evidence)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip-v1")
    output = tmp_path / "shot.mp4"
    output.write_bytes(b"rendered")
    manager = CheckpointManager(tmp_path)
    first = manager.signature(clip, target=4, width=720, height=1280, fps=30, lipsync="off")
    manager.mark_done("shot01", signature=first, output=output, metadata={})

    clip.write_bytes(b"clip-v2")
    second = manager.signature(clip, target=4, width=720, height=1280, fps=30, lipsync="off")
    assert second != first
    assert manager.get("shot01", second) is None

    manager.clear()
    assert not manager.path.exists()


def test_checkpoint_rejects_tampered_output_and_supports_stage_dag(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(checkpoint, "_media_evidence", _fake_media_evidence)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "unit.mp4"
    output.write_bytes(b"valid-output")
    manager = CheckpointManager(tmp_path)
    signature = manager.signature(
        source,
        target=4,
        width=720,
        height=1280,
        fps=30,
        lipsync="off",
    )
    manager.mark_stage_done(
        "unit01",
        "unit_plate",
        signature=signature,
        output=output,
        depends_on=[],
        metadata={"unit_id": "unit01"},
    )

    assert manager.get_stage("unit01", "unit_plate", signature) is not None
    output.write_bytes(b"tampered")
    assert manager.get_stage("unit01", "unit_plate", signature) is None


def test_corrupt_checkpoint_is_preserved_and_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "receipts/checkpoints/final-render.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    manager = CheckpointManager(tmp_path)

    assert manager.corrupt_backup is not None
    assert manager.corrupt_backup.is_file()
    assert manager.data["shots"] == {}
