from __future__ import annotations

import hashlib
import io
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
import sfx_candidates
from sfx_candidates import SFXCandidateError, generate


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
