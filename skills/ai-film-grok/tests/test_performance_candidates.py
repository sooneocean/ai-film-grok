from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from performance_candidates import (
    PerformanceCandidateError,
    approve,
    generate,
    reject,
    sign_receipt,
)


def _wav() -> bytes:
    return b"RIFF" + b"x" * 1024


def test_generate_requires_adult_confirmation(tmp_path: Path) -> None:
    with pytest.raises(PerformanceCandidateError, match="adult_confirmed"):
        generate(
            tmp_path,
            base_url="http://node",
            token="x" * 24,
            cue="nonverbal performance",
            duration=2,
            seed=1,
            character_id="adult_a",
            source_authorization="original",
            adult_confirmed=False,
        )
    with pytest.raises(PerformanceCandidateError, match="adult_confirmed"):
        generate(
            tmp_path,
            base_url="http://node",
            token="x" * 24,
            cue="nonverbal performance",
            duration=2,
            seed=1,
            character_id="adult_a",
            source_authorization="original",
            adult_confirmed="false",  # type: ignore[arg-type]
        )
    with pytest.raises(PerformanceCandidateError, match="take seed"):
        generate(
            tmp_path,
            base_url="http://node",
            token="x" * 24,
            cue="nonverbal performance",
            duration=2,
            seed=True,  # type: ignore[arg-type]
            character_id="adult_a",
            source_authorization="original",
            adult_confirmed=True,
        )


def test_approve_writes_receipt_bound_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 24)
    pending = tmp_path / "audio/candidates/performance/pending"
    pending.mkdir(parents=True)
    asset_id = "performance-adult-a-1-test"
    source = pending / f"{asset_id}.wav"
    source.write_bytes(_wav())
    record = {
        "schema": "aifilm-performance-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "character_id": "adult_a",
        "language": "nonverbal",
        "adult_confirmed": True,
        "source_authorization": "original",
        "model_version": "higgs-audio-v2",
        "node_job_id": "job-1",
        "take_seed": 1,
        "path": f"audio/candidates/performance/pending/{asset_id}.wav",
        "sha256": hashlib.sha256(_wav()).hexdigest(),
    }
    (pending / f"{asset_id}.json").write_text(json.dumps(sign_receipt(record)))
    with patch("performance_candidates._validate_wav"):
        result = approve(tmp_path, asset_id)
    approved = tmp_path / "audio/candidates/performance/approved" / f"{asset_id}.wav"
    assert result["status"] == "approved"
    assert approved.is_file()
    assert approved.with_suffix(".receipt.json").is_file()


def test_approve_wraps_bad_wav_as_candidate_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 24)
    pending = tmp_path / "audio/candidates/performance/pending"
    pending.mkdir(parents=True)
    asset_id = "performance-adult-a-2-bad"
    source = pending / f"{asset_id}.wav"
    source.write_bytes(b"not a wav")
    record = {
        "schema": "aifilm-performance-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "character_id": "adult_a",
        "language": "nonverbal",
        "adult_confirmed": True,
        "source_authorization": "original",
        "model_version": "higgs-audio-v2",
        "node_job_id": "job-2",
        "take_seed": 2,
        "path": f"audio/candidates/performance/pending/{asset_id}.wav",
        "sha256": hashlib.sha256(b"not a wav").hexdigest(),
    }
    (pending / f"{asset_id}.json").write_text(json.dumps(sign_receipt(record)))
    with pytest.raises(PerformanceCandidateError, match="valid delivery WAV"):
        approve(tmp_path, asset_id)


def test_reject_blocks_later_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 24)
    pending = tmp_path / "audio/candidates/performance/pending"
    pending.mkdir(parents=True)
    asset_id = "performance-adult-a-3-reject"
    source = pending / f"{asset_id}.wav"
    source.write_bytes(_wav())
    record = {
        "schema": "aifilm-performance-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "character_id": "adult_a",
        "language": "nonverbal",
        "adult_confirmed": True,
        "source_authorization": "original",
        "model_version": "higgs-audio-v2",
        "node_job_id": "job-3",
        "take_seed": 3,
        "path": f"audio/candidates/performance/pending/{asset_id}.wav",
        "sha256": hashlib.sha256(_wav()).hexdigest(),
    }
    (pending / f"{asset_id}.json").write_text(json.dumps(sign_receipt(record)))
    result = reject(tmp_path, asset_id, reviewer="dex", reason="not a female breath performance")
    assert result["status"] == "rejected_human_review"
    with pytest.raises(PerformanceCandidateError, match="receipt is invalid"):
        approve(tmp_path, asset_id)
