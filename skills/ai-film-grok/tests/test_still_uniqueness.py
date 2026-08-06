from __future__ import annotations

from pathlib import Path

import pytest
from still_uniqueness import (
    StillUniquenessError,
    active_still_reuse_report,
    assert_still_is_unique,
)
from util import sha256_file


def test_rejects_byte_identical_still_for_another_shot(tmp_path: Path) -> None:
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake-still-bytes-aaa")
    sha = sha256_file(img)
    man = {
        "stills": {
            "shot01": {
                "status": "approved",
                "sha256": sha,
                "path": str(img),
            }
        }
    }
    with pytest.raises(StillUniquenessError, match="shot01"):
        assert_still_is_unique(
            root=tmp_path,
            shot_id="shot02",
            source=img,
            status="approved",
            manifest=man,
        )


def test_allows_different_still_bytes(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_bytes(b"\x89PNG\r\n\x1a\n" + b"still-a")
    b.write_bytes(b"\x89PNG\r\n\x1a\n" + b"still-b")
    man = {
        "stills": {
            "shot01": {"status": "approved", "sha256": sha256_file(a), "path": str(a)},
        }
    }
    assert_still_is_unique(
        root=tmp_path, shot_id="shot02", source=b, status="approved", manifest=man
    )


def test_delivery_gate_reports_reuse_groups() -> None:
    report = active_still_reuse_report(
        {
            "stills": {
                "s1": {"status": "approved", "sha256": "aaa"},
                "s2": {"status": "approved", "sha256": "aaa"},
                "s3": {"status": "approved", "sha256": "bbb"},
            }
        },
        required_shot_ids=["s1", "s2", "s3"],
    )
    assert report["ok"] is False
    assert report["duplicate_sha256_groups"] == [["s1", "s2"]]


def test_delivery_gate_uses_the_readable_file_not_a_stale_manifest_sha(tmp_path: Path) -> None:
    image = tmp_path / "same.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"same-still")
    report = active_still_reuse_report(
        {
            "stills": {
                "s1": {"status": "approved", "sha256": "a" * 64, "path": str(image)},
                "s2": {"status": "approved", "sha256": "b" * 64, "path": str(image)},
            }
        },
        required_shot_ids=["s1", "s2"],
    )

    assert report["ok"] is False
    assert report["duplicate_sha256_groups"] == [["s1", "s2"]]


def test_register_gate_uses_the_readable_file_not_a_stale_manifest_sha(tmp_path: Path) -> None:
    image = tmp_path / "same.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"same-still")
    manifest = {
        "stills": {
            "s1": {"status": "approved", "sha256": "a" * 64, "path": str(image)},
        }
    }

    with pytest.raises(StillUniquenessError, match="s1"):
        assert_still_is_unique(
            root=tmp_path,
            shot_id="s2",
            source=image,
            status="approved",
            manifest=manifest,
        )
