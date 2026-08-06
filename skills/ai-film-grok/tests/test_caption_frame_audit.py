from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from caption_frame_audit import (  # noqa: E402
    _sha256,
    attest_caption_readability,
    caption_readability_evidence_status,
    sample_cue_indices,
)
from util import write_json  # noqa: E402


def test_sample_cue_indices_covers_first_middle_and_last() -> None:
    assert sample_cue_indices(9, max_frames=3) == [0, 4, 8]


def test_sample_cue_indices_never_exceeds_available_cues() -> None:
    assert sample_cue_indices(2, max_frames=5) == [0, 1]
    assert sample_cue_indices(0) == []


def test_caption_attestation_requires_current_human_bound_frames(tmp_path: Path) -> None:
    final = tmp_path / "out" / "final.mp4"
    subtitle = tmp_path / "out" / "final.srt"
    frame = tmp_path / "receipts" / "caption-frames" / "caption-01.png"
    for path, content in ((final, b"final"), (subtitle, b"subtitle"), (frame, b"frame")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    audit_path = tmp_path / "receipts" / "caption-frame-audit.json"
    write_json(
        audit_path,
        {
            "kind": "caption-frame-audit",
            "final": {"path": str(final), "sha256": _sha256(final)},
            "subtitles": {"path": str(subtitle), "sha256": _sha256(subtitle)},
            "frames": [{"path": str(frame), "sha256": _sha256(frame)}],
        },
    )

    report = attest_caption_readability(tmp_path, user_phrase="字幕清楚通过")

    assert report["state"] == "human_readability_approved"
    assert caption_readability_evidence_status(tmp_path)["ok"] is True
    with pytest.raises(ValueError, match="approval phrase"):
        attest_caption_readability(tmp_path, user_phrase="字幕不清楚")
