from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from clip_uniqueness import ClipUniquenessError, active_clip_reuse_report, assert_clip_is_unique


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_rejects_exact_clip_reused_by_another_shot(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x90:r=24:d=2",
            "-an",
            "-c:v",
            "libx264",
            str(clip),
        ],
        check=True,
        capture_output=True,
    )
    first = assert_clip_is_unique(clip, manifest={"clips": {}}, shot_id="shot01")
    with pytest.raises(ClipUniquenessError, match="shot01"):
        assert_clip_is_unique(
            clip, manifest={"clips": {"shot01": {"uniqueness": first}}}, shot_id="shot02"
        )


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_allows_a_different_i2v_segment(tmp_path: Path) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    for output, source in ((first, "testsrc2"), (second, "smptebars")):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"{source}=s=160x90:r=24:d=2",
                "-an",
                "-c:v",
                "libx264",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
    known = assert_clip_is_unique(first, manifest={"clips": {}}, shot_id="shot01")
    result = assert_clip_is_unique(
        second, manifest={"clips": {"shot01": {"uniqueness": known}}}, shot_id="shot02"
    )
    assert result["sha256"] != known["sha256"]


def test_delivery_gate_rejects_manifest_injected_duplicate_or_missing_fingerprint() -> None:
    duplicate = active_clip_reuse_report(
        {
            "clips": {
                "shot01": {"status": "approved", "uniqueness": {"sha256": "same"}},
                "shot02": {"status": "approved", "uniqueness": {"sha256": "same"}},
            }
        },
        required_shot_ids=["shot01", "shot02"],
    )
    assert duplicate["ok"] is False
    assert duplicate["duplicate_sha256_groups"] == [["shot01", "shot02"]]

    missing = active_clip_reuse_report(
        {"clips": {"shot01": {"status": "approved"}}}, required_shot_ids=["shot01"]
    )
    assert missing["ok"] is False
    assert missing["missing_fingerprint_shots"] == ["shot01"]
