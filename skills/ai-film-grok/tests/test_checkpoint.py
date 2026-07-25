"""Tests for hash-bound final-render shot checkpoints."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from checkpoint import CheckpointManager


def test_checkpoint_roundtrip_and_resume_requires_matching_signature(tmp_path: Path) -> None:
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
        == 1
    )


def test_checkpoint_invalidates_changed_clip_and_clear(tmp_path: Path) -> None:
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
