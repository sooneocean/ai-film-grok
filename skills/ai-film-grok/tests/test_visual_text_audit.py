from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from visual_text_audit import VisualTextAuditError, audit_clip, require_clean_audit  # noqa: E402
from visual_text_repair import repair_windows  # noqa: E402


def _video(root: Path) -> Path:
    path = root / "clips" / "ltx.mp4"
    path.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=64x64:r=3:d=1",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def test_audit_scans_every_frame_and_binds_clean_receipt(tmp_path: Path) -> None:
    clip = _video(tmp_path)
    report = audit_clip(
        tmp_path, clip, base_url="http://127.0.0.1:1/v1", model="test", review_batch=lambda *_: []
    )
    assert report["status"] == "clean"
    assert report["sampling"]["mode"] == "every_decoded_frame"
    assert report["sampling"]["frame_count"] == 3
    assert require_clean_audit(tmp_path, clip)["status"] == "clean"
    clip.write_bytes(b"changed")
    with pytest.raises(VisualTextAuditError, match="stale"):
        require_clean_audit(tmp_path, clip)


def test_audit_rejects_a_single_detected_frame(tmp_path: Path) -> None:
    clip = _video(tmp_path)
    report = audit_clip(
        tmp_path,
        clip,
        base_url="http://127.0.0.1:1/v1",
        model="test",
        review_batch=lambda *_: [{"frame_index": 0, "location": "upper right", "confidence": 0.9}],
    )
    assert report["reason"] == "PROVIDER_VISUAL_TEXT_REJECTED"
    assert report["findings"][0]["index"] == 0
    with pytest.raises(VisualTextAuditError, match="PROVIDER_VISUAL_TEXT_REJECTED"):
        require_clean_audit(tmp_path, clip)


def test_repair_windows_extend_merge_and_clamp() -> None:
    assert repair_windows([0, 3, 9], frame_count=10) == [(0, 5), (7, 9)]
