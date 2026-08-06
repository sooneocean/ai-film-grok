from __future__ import annotations

import hashlib
import io
import json
import wave
from pathlib import Path

import ambience_candidates
import pytest
from ambience_candidates import AmbienceCandidateError, approve, attach_to_shot
from performance_candidates import sign_receipt
from util import write_json


def test_approve_rejects_symlinked_pending_wav(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 32)
    asset_id = "ambience-test"
    pending = tmp_path / "audio" / "candidates" / "ambience" / "pending"
    pending.mkdir(parents=True)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"not-a-real-wav")
    source = pending / f"{asset_id}.wav"
    source.symlink_to(outside)
    record = {
        "schema": "aifilm-ambience-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    sign_receipt(record)
    write_json(pending / f"{asset_id}.json", record)
    monkeypatch.setattr(ambience_candidates, "_validate_wav", lambda _path: None)

    with pytest.raises(AmbienceCandidateError, match="local pending file"):
        approve(
            tmp_path,
            asset_id,
            reviewer="Dex",
            heard_full=True,
            no_speech_confirmed=True,
            no_music_confirmed=True,
            artifact_free_confirmed=True,
        )


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\0\0\0\0" * 44100)
    return buffer.getvalue()


def _pending(root: Path, asset_id: str = "ambience-11-test") -> None:
    pending = root / "audio" / "candidates" / "ambience" / "pending"
    pending.mkdir(parents=True)
    wav = pending / f"{asset_id}.wav"
    wav.write_bytes(_wav())
    record = {
        "schema": "aifilm-ambience-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "kind": "ambience",
        "model": "stable-audio-open-1.0",
        "license": "Stability AI Community License",
        "checkpoint_sha256": "b" * 64,
        "adapter_sha256": "c" * 64,
        "production_eligible": False,
        "take_seed": 11,
        "duration_sec": 1.0,
        "node_job_id": "ambient-job-1",
        "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "prompt_sha256": "a" * 64,
        "path": str(wav.relative_to(root)),
        "created_at": "2026-07-30T00:00:00+00:00",
    }
    sign_receipt(record)
    write_json(pending / f"{asset_id}.json", record)


def test_approve_and_attach_internal_noncommercial_ambience(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 32)
    _pending(tmp_path)
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "shot01", "duration_sec": 3.0}]}]}),
        encoding="utf-8",
    )
    approved = approve(
        tmp_path,
        "ambience-11-test",
        reviewer="dex",
        heard_full=True,
        no_speech_confirmed=True,
        no_music_confirmed=True,
        artifact_free_confirmed=True,
    )
    assert approved["status"] == "approved_noncommercial"
    attached = attach_to_shot(
        tmp_path,
        "ambience-11-test",
        shot_id="shot01",
        start_offset_sec=0,
        duration_sec=3,
        acoustic_space="night shelter room tone",
        noncommercial_internal_ok=True,
    )
    assert attached["cue"]["kind"] == "ambience"
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    assert spec["delivery_scope"] == "noncommercial_internal"


def test_approve_requires_full_listening_attestation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 32)
    _pending(tmp_path)
    with pytest.raises(AmbienceCandidateError, match="complete explicit listening review"):
        approve(
            tmp_path,
            "ambience-11-test",
            reviewer="dex",
            heard_full=True,
            no_speech_confirmed=False,
            no_music_confirmed=True,
            artifact_free_confirmed=True,
        )


def test_approve_rejects_symlinked_approval_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 32)
    _pending(tmp_path)
    approved_parent = tmp_path / "audio" / "candidates" / "ambience"
    outside = tmp_path / "outside"
    outside.mkdir()
    (approved_parent / "approved-noncommercial").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AmbienceCandidateError, match="output already exists"):
        approve(
            tmp_path,
            "ambience-11-test",
            reviewer="dex",
            heard_full=True,
            no_speech_confirmed=True,
            no_music_confirmed=True,
            artifact_free_confirmed=True,
        )
    assert not list(outside.iterdir())
