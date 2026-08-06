from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from review_pack import (  # noqa: E402
    ReviewPackError,
    build_review_pack,
    comfy_download_target,
    ensure_review_pack_available,
)
from security_policy import SecurityPolicyError  # noqa: E402


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_local_review_pack_is_hash_bound_and_never_approves() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "candidate.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=160x90:r=24:d=2",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=44100:d=2",
                "-shortest",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(source),
            ],
            check=True,
            capture_output=True,
        )

        report = build_review_pack(root, pack_id="candidate-a", source=source)

        assert report["ok"] is True
        assert report["approved"] is False
        assert report["human_review_required"] is True
        assert len(report["artifacts"]["frames"]) == 3
        assert Path(report["artifacts"]["contact_sheet"]["path"]).is_file()
        assert Path(report["path"]).is_file()
        assert len(report["source"]["sha256"]) == 64


def test_review_pack_rejects_duplicate_package_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / "receipts" / "review-packs" / "taken"
        target.mkdir(parents=True)
        with pytest.raises(ReviewPackError, match="already exists"):
            build_review_pack(root, pack_id="taken", source=root / "missing.mp4")


def test_comfy_download_target_validates_id_before_constructing_a_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with pytest.raises(SecurityPolicyError):
            comfy_download_target(root, pack_id="../../escaped", filename="candidate.mp4")
        assert comfy_download_target(root, pack_id="candidate-a", filename="candidate.mp4") == (
            root.resolve() / "receipts" / "review-inputs" / "candidate-a.mp4"
        )


def test_comfy_download_refuses_reused_pack_or_input_path(tmp_path: Path) -> None:
    package = tmp_path / "receipts" / "review-packs" / "taken"
    package.mkdir(parents=True)
    with pytest.raises(ReviewPackError, match="already exists"):
        ensure_review_pack_available(tmp_path, pack_id="taken")

    target = tmp_path / "receipts" / "review-inputs" / "fresh.mp4"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")
    with pytest.raises(ReviewPackError, match="already exists"):
        comfy_download_target(tmp_path, pack_id="fresh", filename="remote.mp4")
