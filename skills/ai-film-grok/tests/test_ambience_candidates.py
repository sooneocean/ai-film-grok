from __future__ import annotations

import hashlib

import pytest

import ambience_candidates
from ambience_candidates import AmbienceCandidateError, approve
from util import write_json


def test_approve_rejects_symlinked_pending_wav(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    asset_id = "ambience-test"
    pending = tmp_path / "audio" / "candidates" / "ambience" / "pending"
    pending.mkdir(parents=True)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"not-a-real-wav")
    source = pending / f"{asset_id}.wav"
    source.symlink_to(outside)
    write_json(
        pending / f"{asset_id}.json",
        {
            "schema": "aifilm-ambience-candidate-v1",
            "status": "pending_human_review",
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        },
    )
    monkeypatch.setattr(ambience_candidates, "_validate_wav", lambda _path: None)

    with pytest.raises(AmbienceCandidateError, match="local pending file"):
        approve(tmp_path, asset_id, reviewer="Dex")
