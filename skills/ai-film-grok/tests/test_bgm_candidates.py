from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from bgm_candidates import BGMCandidateError, approve, generate


def _wav() -> bytes:
    return b"RIFF" + b"x" * 1024


def test_generate_is_pending_and_does_not_store_prompt(tmp_path: Path) -> None:
    def fake_render(_base, _token, _kind, _payload, out, timeout=900):
        del timeout
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_wav())
        return {"job_id": "job-1", "sha256": hashlib.sha256(_wav()).hexdigest()}

    with (
        patch("bgm_candidates.render", side_effect=fake_render),
        patch("bgm_candidates._validate_wav"),
    ):
        result = generate(
            tmp_path,
            base_url="http://node",
            token="x" * 24,
            prompt="private scene music direction",
            mood="RNB",
            duration=10,
            seed=7,
        )

    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["status"] == "pending_human_review"
    assert "prompt" not in receipt
    assert receipt["prompt_sha256"]


def test_approve_promotes_only_hash_valid_candidate(tmp_path: Path) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    source = pending / "rnb-1-test.wav"
    source.write_bytes(_wav())
    receipt = pending / "rnb-1-test.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": "rnb",
                "path": "audio/candidates/bgm/pending/rnb-1-test.wav",
                "sha256": hashlib.sha256(_wav()).hexdigest(),
            }
        )
    )

    with patch("bgm_candidates._validate_wav"):
        result = approve(tmp_path, "rnb-1-test")
    assert result["status"] == "approved"
    assert (tmp_path / "audio/templates/rnb/rnb-1-test.wav").is_file()


def test_approve_rejects_changed_candidate(tmp_path: Path) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    (pending / "rnb-1-test.wav").write_bytes(b"changed")
    (pending / "rnb-1-test.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": "rnb",
                "path": "audio/candidates/bgm/pending/rnb-1-test.wav",
                "sha256": "0" * 64,
            }
        )
    )
    with pytest.raises(BGMCandidateError, match="hash"):
        approve(tmp_path, "rnb-1-test")


def test_approve_rejects_copy_that_changes_bytes(tmp_path: Path) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    source = pending / "rnb-1-test.wav"
    source.write_bytes(_wav())
    (pending / "rnb-1-test.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": "rnb",
                "path": "audio/candidates/bgm/pending/rnb-1-test.wav",
                "sha256": hashlib.sha256(_wav()).hexdigest(),
            }
        )
    )

    def corrupt_copy(_source: Path, target: Path) -> Path:
        target.write_bytes(b"changed during copy")
        return target

    with (
        patch("bgm_candidates.shutil.copyfile", side_effect=corrupt_copy),
        patch("bgm_candidates._validate_wav"),
        pytest.raises(BGMCandidateError, match="changed while"),
    ):
        approve(tmp_path, "rnb-1-test")
    assert not (tmp_path / "audio/templates/rnb/rnb-1-test.wav").exists()


def test_approve_rejects_symlinked_candidate(tmp_path: Path) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(_wav())
    source = pending / "rnb-1-test.wav"
    source.symlink_to(outside)
    (pending / "rnb-1-test.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": "rnb",
                "path": "audio/candidates/bgm/pending/rnb-1-test.wav",
                "sha256": hashlib.sha256(_wav()).hexdigest(),
            }
        )
    )
    with pytest.raises(BGMCandidateError, match="missing"):
        approve(tmp_path, "rnb-1-test")


def test_approve_rejects_symlinked_template_directory(tmp_path: Path) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    source = pending / "rnb-1-test.wav"
    source.write_bytes(_wav())
    (pending / "rnb-1-test.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": "rnb",
                "path": "audio/candidates/bgm/pending/rnb-1-test.wav",
                "sha256": hashlib.sha256(_wav()).hexdigest(),
            }
        )
    )
    outside = tmp_path / "outside-templates"
    outside.mkdir()
    template_root = tmp_path / "audio/templates"
    template_root.symlink_to(outside, target_is_directory=True)
    with patch("bgm_candidates._validate_wav"), pytest.raises(BGMCandidateError, match="directory"):
        approve(tmp_path, "rnb-1-test")


@pytest.mark.parametrize(
    ("mood", "path", "message"),
    [
        ("../../escaped", "audio/candidates/bgm/pending/rnb-1-test.wav", "mood"),
        ("rnb", "/tmp/not-a-candidate.wav", "path"),
    ],
)
def test_approve_rejects_unconfined_receipt_fields(
    tmp_path: Path, mood: str, path: str, message: str
) -> None:
    pending = tmp_path / "audio/candidates/bgm/pending"
    pending.mkdir(parents=True)
    (pending / "rnb-1-test.wav").write_bytes(_wav())
    (pending / "rnb-1-test.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-bgm-candidate-v1",
                "asset_id": "rnb-1-test",
                "status": "pending_human_review",
                "mood": mood,
                "path": path,
                "sha256": hashlib.sha256(_wav()).hexdigest(),
            }
        )
    )
    with pytest.raises(BGMCandidateError, match=message):
        approve(tmp_path, "rnb-1-test")
