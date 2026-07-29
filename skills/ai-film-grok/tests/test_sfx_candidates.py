from __future__ import annotations

import hashlib
import io
import json
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
import sfx_candidates
from sfx_candidates import SFXCandidateError, approve, attach_to_shot, generate, reject


def _delivery_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\0\0\0\0" * 44100)
    return buffer.getvalue()


def test_generate_requires_explicit_noncommercial_ack(tmp_path: Path) -> None:
    with pytest.raises(SFXCandidateError, match="CC BY-NC"):
        generate(
            tmp_path,
            prompt="door closes",
            duration=1,
            seed=1,
            source_video=None,
            noncommercial_research_ok=False,
        )


def test_generate_stays_pending_and_never_production_eligible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    wav = _delivery_wav()

    def fake_render(_base, _token, **kwargs):
        kwargs["out"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["out"].write_bytes(wav)
        return {
            "job_id": "job",
            "sha256": hashlib.sha256(wav).hexdigest(),
            "model": "hkchengrex/MMAudio-large-44k-v2",
            "checkpoint_fingerprint": "a" * 64,
            "license": "CC-BY-NC-4.0",
            "source_video_sha256": None,
        }

    with patch("sfx_candidates.render_sfx", side_effect=fake_render):
        report = generate(
            tmp_path,
            prompt="door closes",
            duration=1,
            seed=1,
            source_video=None,
            noncommercial_research_ok=True,
        )

    assert report["status"] == "pending_human_review"
    assert report["production_eligible"] is False
    assert report["usage_scope"] == "noncommercial_internal_research"
    assert "door closes" not in str(report)
    assert Path(report["receipt"]).is_file()


def test_generate_discards_wrong_duration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    wav = _delivery_wav()

    def fake_render(_base, _token, **kwargs):
        kwargs["out"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["out"].write_bytes(wav)
        return {
            "job_id": "job",
            "sha256": hashlib.sha256(wav).hexdigest(),
            "model": "hkchengrex/MMAudio-large-44k-v2",
            "checkpoint_fingerprint": "a" * 64,
            "license": "CC-BY-NC-4.0",
            "source_video_sha256": None,
        }

    with patch("sfx_candidates.render_sfx", side_effect=fake_render):
        with pytest.raises(SFXCandidateError, match="duration mismatch"):
            generate(
                tmp_path,
                prompt="door closes",
                duration=8,
                seed=1,
                source_video=None,
                noncommercial_research_ok=True,
            )

    assert not list((tmp_path / "audio" / "candidates" / "sfx").rglob("*.wav"))


def test_generate_rejects_symlinked_pending_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    outside = tmp_path / "outside"
    outside.mkdir()
    candidates = tmp_path / "film" / "audio" / "candidates" / "sfx"
    candidates.mkdir(parents=True)
    (candidates / "pending").symlink_to(outside, target_is_directory=True)

    with pytest.raises(SFXCandidateError, match="symlinks"):
        generate(
            tmp_path / "film",
            prompt="door closes",
            duration=1,
            seed=1,
            source_video=None,
            noncommercial_research_ok=True,
        )
    assert not list(outside.iterdir())


def test_generate_rechecks_pending_after_remote_render(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    film = tmp_path / "film"
    outside = tmp_path / "outside"
    outside.mkdir()
    wav = _delivery_wav()

    def fake_render(_base, _token, **kwargs):
        kwargs["out"].write_bytes(wav)
        candidates = film / "audio" / "candidates" / "sfx"
        pending = candidates / "pending"
        pending.rename(candidates / "pending-original")
        (candidates / "pending").symlink_to(outside, target_is_directory=True)
        return {
            "job_id": "job",
            "sha256": hashlib.sha256(wav).hexdigest(),
            "model": "hkchengrex/MMAudio-large-44k-v2",
            "checkpoint_fingerprint": "a" * 64,
            "license": "CC-BY-NC-4.0",
            "source_video_sha256": None,
        }

    with patch("sfx_candidates.render_sfx", side_effect=fake_render):
        with pytest.raises(SFXCandidateError, match="symlinks"):
            generate(
                film,
                prompt="door closes",
                duration=1,
                seed=1,
                source_video=None,
                noncommercial_research_ok=True,
            )
    assert not list(outside.iterdir())


def test_generate_cannot_follow_symlink_swapped_at_final_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    film = tmp_path / "film"
    outside = tmp_path / "outside"
    outside.mkdir()
    wav = _delivery_wav()

    def fake_render(_base, _token, **kwargs):
        kwargs["out"].write_bytes(wav)
        return {
            "job_id": "job",
            "sha256": hashlib.sha256(wav).hexdigest(),
            "model": "hkchengrex/MMAudio-large-44k-v2",
            "checkpoint_fingerprint": "a" * 64,
            "license": "CC-BY-NC-4.0",
            "source_video_sha256": None,
        }

    original_copy = sfx_candidates._copy_into_open_directory
    swapped = False

    def race_copy(directory_fd, source, final_name):
        nonlocal swapped
        if not swapped:
            swapped = True
            candidates = film / "audio" / "candidates" / "sfx"
            pending = candidates / "pending"
            pending.rename(candidates / "pending-original")
            pending.symlink_to(outside, target_is_directory=True)
        return original_copy(directory_fd, source, final_name)

    with (
        patch("sfx_candidates.render_sfx", side_effect=fake_render),
        patch("sfx_candidates._copy_into_open_directory", side_effect=race_copy),
    ):
        with pytest.raises(SFXCandidateError, match="changed during promotion"):
            generate(
                film,
                prompt="door closes",
                duration=1,
                seed=1,
                source_video=None,
                noncommercial_research_ok=True,
            )

    assert not list(outside.iterdir())
    assert not list((film / "audio" / "candidates" / "sfx" / "pending-original").iterdir())


def _pending_candidate(root: Path, asset_id: str = "mmaudio-sfx-1-abc123") -> tuple[Path, Path]:
    pending = root / "audio" / "candidates" / "sfx" / "pending"
    pending.mkdir(parents=True)
    wav = pending / f"{asset_id}.wav"
    wav.write_bytes(_delivery_wav())
    record = {
        "schema": "aifilm-sfx-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "production_eligible": False,
        "usage_scope": "noncommercial_internal_research",
        "license": "CC-BY-NC-4.0",
        "model": "hkchengrex/MMAudio-large-44k-v2",
        "checkpoint_fingerprint": "a" * 64,
        "seed": 1,
        "duration_sec": 1.0,
        "requested_duration_sec": 1.0,
        "node_job_id": "job-1",
        "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
        "prompt_sha256": "b" * 64,
        "source_video_sha256": "c" * 64,
        "path": str(wav.relative_to(root)),
        "created_at": "2026-07-29T00:00:00+00:00",
    }
    sfx_candidates.sign_receipt(record)
    receipt = pending / f"{asset_id}.json"
    receipt.write_text(json.dumps(record), encoding="utf-8")
    return wav, receipt


def test_approve_requires_complete_human_listening_attestation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(tmp_path)

    with pytest.raises(SFXCandidateError, match="listening checks"):
        approve(
            tmp_path,
            "mmaudio-sfx-1-abc123",
            reviewer="dex",
            heard_full=True,
            sync_confirmed=True,
            no_speech_confirmed=False,
            no_music_confirmed=True,
            artifact_free_confirmed=True,
        )


def test_approve_does_not_follow_preexisting_partial_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(tmp_path)
    approved = tmp_path / "audio" / "candidates" / "sfx" / "approved-noncommercial"
    approved.mkdir(parents=True)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"do-not-overwrite")
    legacy_partial = approved / "mmaudio-sfx-1-abc123.partial.wav"
    legacy_partial.symlink_to(outside)

    approve(
        tmp_path,
        "mmaudio-sfx-1-abc123",
        reviewer="dex",
        heard_full=True,
        sync_confirmed=True,
        no_speech_confirmed=True,
        no_music_confirmed=True,
        artifact_free_confirmed=True,
    )

    assert outside.read_bytes() == b"do-not-overwrite"


def test_approve_and_attach_noncommercial_sfx_to_shot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _, pending_receipt = _pending_candidate(tmp_path)
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "SFX test",
                "vo_mode": "storyteller",
                "director_intent": {"logline": "test"},
                "scenes": [{"id": "scene01", "shots": [{"id": "shot01", "duration_sec": 3.0}]}],
            }
        ),
        encoding="utf-8",
    )

    approved = approve(
        tmp_path,
        "mmaudio-sfx-1-abc123",
        reviewer="dex",
        heard_full=True,
        sync_confirmed=True,
        no_speech_confirmed=True,
        no_music_confirmed=True,
        artifact_free_confirmed=True,
    )
    assert approved["status"] == "approved_noncommercial"
    assert approved["production_eligible"] is False
    assert Path(approved["approval_receipt"]).is_file()
    assert json.loads(pending_receipt.read_text())["status"] == "approved_noncommercial"

    attached = attach_to_shot(
        tmp_path,
        "mmaudio-sfx-1-abc123",
        shot_id="shot01",
        kind="foley",
        start_offset_sec=0.5,
        duration_sec=1.0,
        material="wood",
        noncommercial_internal_ok=True,
    )
    cue = attached["cue"]
    assert cue["approval_status"] == "approved_noncommercial"
    assert cue["usage_scope"] == "noncommercial_internal"
    assert cue["production_eligible"] is False
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    assert spec["delivery_scope"] == "noncommercial_internal"
    assert spec["scenes"][0]["shots"][0]["audio_cues"] == [cue]


def test_attach_rejects_commercial_or_unacknowledged_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(tmp_path)
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "SFX test",
                "vo_mode": "storyteller",
                "director_intent": {"logline": "test"},
                "delivery_scope": "commercial",
                "scenes": [{"id": "scene01", "shots": [{"id": "shot01", "duration_sec": 3.0}]}],
            }
        ),
        encoding="utf-8",
    )
    approve(
        tmp_path,
        "mmaudio-sfx-1-abc123",
        reviewer="dex",
        heard_full=True,
        sync_confirmed=True,
        no_speech_confirmed=True,
        no_music_confirmed=True,
        artifact_free_confirmed=True,
    )

    with pytest.raises(SFXCandidateError, match="non-commercial"):
        attach_to_shot(
            tmp_path,
            "mmaudio-sfx-1-abc123",
            shot_id="shot01",
            kind="foley",
            start_offset_sec=0,
            duration_sec=1,
            material="wood",
            noncommercial_internal_ok=False,
        )


def test_reject_prevents_later_approval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    _pending_candidate(tmp_path)
    rejected = reject(
        tmp_path,
        "mmaudio-sfx-1-abc123",
        reviewer="dex",
        reason="speech leakage",
    )
    assert rejected["status"] == "rejected_human_review"
    with pytest.raises(SFXCandidateError, match="pending"):
        approve(
            tmp_path,
            "mmaudio-sfx-1-abc123",
            reviewer="dex",
            heard_full=True,
            sync_confirmed=True,
            no_speech_confirmed=True,
            no_music_confirmed=True,
            artifact_free_confirmed=True,
        )
