from __future__ import annotations

import hashlib
import io
import json
import wave
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from audio_node_client import (
    AudioNodeError,
    _request,
    _url,
    health,
    public_health_report,
    render,
    render_ambient,
    render_batch,
    render_sfx,
)


def _delivery_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\0\0\0\0" * 4410)
    return buffer.getvalue()


def test_rejects_non_http_node_url() -> None:
    with pytest.raises(AudioNodeError):
        _url("ssh://host", "/health")
    with pytest.raises(AudioNodeError):
        _url("https://example.com", "/health")
    with pytest.raises(AudioNodeError):
        _url("https://169.254.169.254", "/health")
    with pytest.raises(AudioNodeError):
        _url("http://192.168.88.52:8788?token=leak", "/health")
    with pytest.raises(AudioNodeError, match="loopback-only"):
        _url("http://192.168.88.52:8788", "/health")
    assert _url("http://127.0.0.1:8788", "/health") == "http://127.0.0.1:8788/health"
    assert _url("https://192.168.88.52:8788", "/health") == ("https://192.168.88.52:8788/health")


def test_health_requires_private_token() -> None:
    with pytest.raises(AudioNodeError):
        health("http://192.168.88.52:8788", "short")


def test_public_health_report_drops_unknown_fields_and_current_token() -> None:
    token = "private-test-token"
    report = public_health_report(
        {
            "ok": True,
            "node": "private-lan",
            "models": {"tts": True, "music": False, "leak": token},
            "model": token,
            "music_model": "ACE-Step-1.5",
            "performance_model": "bosonai/higgs-audio-v2-generation",
            "gpu": {
                "available": True,
                "name": token,
                "driver": "untrusted diagnostic text",
                "free_vram_mib": 1234,
            },
            "diagnostic": {"secret": token},
        },
        secret_values=(token,),
    )

    assert report == {
        "ok": True,
        "node": "private-lan",
        "models": {"tts": True, "music": False},
        "music_model": "ACE-Step-1.5",
        "performance_model": "bosonai/higgs-audio-v2-generation",
        "gpu": {"available": True, "free_vram_mib": 1234},
    }


def test_public_health_report_keeps_only_known_tts_variant_flags() -> None:
    report = public_health_report(
        {
            "ok": True,
            "tts_variants": {
                "voice_design": True,
                "custom_1_7b": False,
                "custom_0_6b": True,
                "untrusted_variant": True,
            },
        }
    )

    assert report["tts_variants"] == {
        "voice_design": True,
        "custom_1_7b": False,
        "custom_0_6b": True,
    }


def test_public_health_report_drops_allowlisted_windows_path() -> None:
    report = public_health_report(
        {"ok": True, "ambient_model": r"C:\\AI_Models\\stable-audio-open-1.0\\model.safetensors"}
    )
    assert "ambient_model" not in report


def test_public_health_report_drops_filesystem_like_gpu_strings() -> None:
    report = public_health_report(
        {"ok": True, "gpu": {"name": r"C:\\private\\gpu", "cuda": "/private/cuda"}}
    )
    assert "gpu" not in report


def test_http_error_is_not_misreported_as_network_unreachable() -> None:
    error = HTTPError("http://node/health", 404, "Not Found", {}, io.BytesIO())
    with patch("urllib.request.OpenerDirector.open", side_effect=error):
        with pytest.raises(AudioNodeError, match="HTTP 404"):
            _request("http://127.0.0.1:8788", "x" * 32, "/health")


def test_cross_origin_redirect_is_rejected_without_forwarding_token() -> None:
    error = HTTPError(
        "http://192.168.88.52:8788/health",
        302,
        "Found",
        {"Location": "http://192.168.88.53:8788/steal"},
        io.BytesIO(),
    )
    with patch("urllib.request.OpenerDirector.open", side_effect=error):
        with pytest.raises(AudioNodeError, match="HTTP 302"):
            _request("http://127.0.0.1:8788", "x" * 32, "/health")


def test_render_rejects_unknown_kind(tmp_path: Path) -> None:
    with pytest.raises(AudioNodeError):
        render("http://192.168.88.52:8788", "x" * 32, "video", {}, tmp_path / "x.wav")


def test_render_allows_explicit_performance_track(tmp_path: Path) -> None:
    wav = _delivery_wav()
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": hashlib.sha256(wav).hexdigest()}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        receipt = render(
            "http://192.168.88.52:8788",
            "x" * 32,
            "performance",
            {"prompt": "nonverbal performance"},
            tmp_path / "performance.wav",
        )
    assert receipt["path"].endswith("performance.wav")


def test_render_sfx_requires_noncommercial_ack(tmp_path: Path) -> None:
    with pytest.raises(AudioNodeError, match="non-commercial"):
        render_sfx(
            "http://192.168.88.52:8788",
            "x" * 32,
            prompt="door closes",
            duration=8,
            seed=1,
            out=tmp_path / "sfx.wav",
        )


def test_render_ambient_requires_trusted_candidate_capability(tmp_path: Path) -> None:
    with (
        patch(
            "audio_node_client.health",
            return_value={
                "ok": True,
                "models": {"ambient": True},
                "ambient_model": "stabilityai/stable-audio-open-1.0",
                "ambient_license": "Stability AI Community License",
                "ambient_checkpoint_sha256": "c" * 64,
                "ambient_adapter_sha256": "d" * 64,
            },
        ),
        patch(
            "audio_node_client.render",
            return_value={"job_id": "job", "sha256": "b" * 64, "path": "ambient.wav"},
        ) as submit,
    ):
        result = render_ambient(
            "http://192.168.88.52:8788",
            "x" * 32,
            prompt="rain on glass",
            duration=8,
            seed=9,
            out=tmp_path / "ambient.wav",
        )
    assert result["model"] == "stabilityai/stable-audio-open-1.0"
    assert result["status"] == "pending_human_review"
    assert result["production_eligible"] is False
    assert result["usage_scope"] == "stable_audio_community_license_candidate"
    assert result["checkpoint_sha256"] == "c" * 64
    assert result["adapter_sha256"] == "d" * 64
    assert submit.call_args.args[2] == "ambient"
    assert submit.call_args.args[3]["stable_audio_candidate_only"] is True


def test_render_ambient_rejects_wrong_license_provenance(tmp_path: Path) -> None:
    with (
        patch(
            "audio_node_client.health",
            return_value={
                "ok": True,
                "models": {"ambient": True},
                "ambient_model": "stabilityai/stable-audio-open-1.0",
                "ambient_license": "MIT",
            },
        ),
        patch("audio_node_client.render") as submit,
        pytest.raises(AudioNodeError, match="capability"),
    ):
        render_ambient(
            "http://192.168.88.52:8788",
            "x" * 32,
            prompt="rain on glass",
            duration=8,
            seed=9,
            out=tmp_path / "ambient.wav",
        )
    submit.assert_not_called()


def test_render_sfx_rejects_invalid_request_before_health_or_upload(tmp_path: Path) -> None:
    with patch("audio_node_client.health") as node_health:
        with pytest.raises(AudioNodeError, match="duration"):
            render_sfx(
                "http://192.168.88.52:8788",
                "x" * 32,
                prompt="door closes",
                duration=31,
                seed=1,
                out=tmp_path / "sfx.wav",
                noncommercial_research_ok=True,
            )
    node_health.assert_not_called()


def test_render_sfx_fails_before_submission_when_capability_is_untrusted(
    tmp_path: Path,
) -> None:
    with (
        patch(
            "audio_node_client.health",
            return_value={
                "ok": True,
                "models": {"sfx": True},
                "sfx_model": "unknown",
                "sfx_license": "commercial",
                "sfx_checkpoint_fingerprint": "a" * 64,
            },
        ),
        patch("audio_node_client.render") as submit,
    ):
        with pytest.raises(AudioNodeError, match="unavailable"):
            render_sfx(
                "http://192.168.88.52:8788",
                "x" * 32,
                prompt="door closes",
                duration=8,
                seed=1,
                out=tmp_path / "sfx.wav",
                noncommercial_research_ok=True,
            )
    submit.assert_not_called()


def test_render_sfx_uploads_hash_bound_video_without_local_path(tmp_path: Path) -> None:
    source = tmp_path / "private-shot.mp4"
    source.write_bytes(b"video" * 512)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    captured: list[tuple[str, dict[str, object]]] = []

    def fake_request(*args, **kwargs):
        captured.append((args[2], kwargs))
        return json.dumps({"source_id": source_hash, "source_sha256": source_hash}).encode()

    with (
        patch(
            "audio_node_client.health",
            return_value={
                "ok": True,
                "models": {"sfx": True},
                "sfx_model": "hkchengrex/MMAudio-large-44k-v2",
                "sfx_license": "CC-BY-NC-4.0",
                "sfx_checkpoint_fingerprint": "a" * 64,
            },
        ),
        patch("audio_node_client._request", side_effect=fake_request),
        patch(
            "audio_node_client.render",
            return_value={"job_id": "job", "sha256": "b" * 64, "path": "sfx.wav"},
        ) as submit,
    ):
        result = render_sfx(
            "http://192.168.88.52:8788",
            "x" * 32,
            prompt="door closes",
            duration=8,
            seed=1,
            out=tmp_path / "sfx.wav",
            source_video=source,
            noncommercial_research_ok=True,
        )

    assert captured[0][0] == "/v1/sfx-source"
    payload = submit.call_args.args[3]
    assert payload["source_video_id"] == source_hash
    assert str(source) not in json.dumps(payload)
    assert result["source_video_sha256"] == source_hash


def test_render_rejects_non_wav_result(tmp_path: Path) -> None:
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed"}).encode(),
            b"not-wav",
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="invalid wav"):
            render(
                "http://192.168.88.52:8788",
                "x" * 32,
                "tts",
                {"text": "x"},
                tmp_path / "x.wav",
            )


def test_render_requires_receipt_hash_and_delivery_format(tmp_path: Path) -> None:
    wav = _delivery_wav()
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": hashlib.sha256(wav).hexdigest()}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        receipt = render(
            "http://192.168.88.52:8788",
            "x" * 32,
            "tts",
            {"text": "x"},
            tmp_path / "x.wav",
        )

    assert receipt["sha256"] == hashlib.sha256(wav).hexdigest()


def test_render_discards_hash_mismatch(tmp_path: Path) -> None:
    wav = _delivery_wav()
    output = tmp_path / "x.wav"
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": "0" * 64}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="hash"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, output)

    assert not output.exists()


def test_render_preserves_existing_asset_when_candidate_is_rejected(tmp_path: Path) -> None:
    wav = _delivery_wav()
    output = tmp_path / "x.wav"
    output.write_bytes(b"existing approved asset")
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": "0" * 64}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="hash"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, output)

    assert output.read_bytes() == b"existing approved asset"


def test_render_rejects_unknown_terminal_state(tmp_path: Path) -> None:
    replies = iter(
        [json.dumps({"job_id": "a"}).encode(), json.dumps({"status": "cancelled"}).encode()]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="unknown terminal"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, tmp_path / "x.wav")


def test_render_wraps_invalid_submission_json(tmp_path: Path) -> None:
    with patch("audio_node_client._request", return_value=b"not-json"):
        with pytest.raises(AudioNodeError, match="submission JSON"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, tmp_path / "x.wav")


def test_render_batch_downloads_every_hash_bound_artifact(tmp_path: Path) -> None:
    wav_a = _delivery_wav()
    wav_b = _delivery_wav() + b"distinct"
    replies = iter(
        [
            json.dumps({"job_id": "batch"}).encode(),
            json.dumps(
                {
                    "status": "completed",
                    "model": "ACE-Step-1.5",
                    "checkpoint_fingerprint": "checkpoint",
                    "artifacts": [
                        {"index": 0, "seed": 1, "sha256": hashlib.sha256(wav_a).hexdigest()},
                        {"index": 1, "seed": 2, "sha256": hashlib.sha256(wav_b).hexdigest()},
                    ],
                }
            ).encode(),
            wav_a,
            wav_b,
        ]
    )
    with (
        patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)),
        patch("audio_node_client._validate_wav"),
    ):
        receipt = render_batch(
            "http://192.168.88.52:8788",
            "x" * 32,
            payload={"prompt": "instrumental", "batch_size": 2, "seeds": [1, 2]},
            out_dir=tmp_path / "batch",
        )

    assert [item["seed"] for item in receipt["artifacts"]] == [1, 2]
    assert all(Path(item["path"]).is_file() for item in receipt["artifacts"])


def test_render_batch_removes_partial_outputs_on_hash_mismatch(tmp_path: Path) -> None:
    wav = _delivery_wav()
    replies = iter(
        [
            json.dumps({"job_id": "batch"}).encode(),
            json.dumps(
                {
                    "status": "completed",
                    "artifacts": [{"index": 0, "seed": 1, "sha256": "0" * 64}],
                }
            ).encode(),
            wav,
        ]
    )
    output = tmp_path / "batch"
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="hash"):
            render_batch(
                "http://192.168.88.52:8788",
                "x" * 32,
                payload={"prompt": "instrumental", "batch_size": 1, "seeds": [1]},
                out_dir=output,
            )
    assert not list(output.glob("*.wav"))


def test_render_batch_uploads_reference_without_sending_local_path(tmp_path: Path) -> None:
    reference = tmp_path / "private-series-master.wav"
    raw_reference = _delivery_wav()
    reference.write_bytes(raw_reference)
    generated = _delivery_wav()
    captured: list[tuple[str, dict[str, object]]] = []
    replies = iter(
        [
            json.dumps(
                {
                    "reference_id": hashlib.sha256(raw_reference).hexdigest(),
                    "source_sha256": hashlib.sha256(raw_reference).hexdigest(),
                }
            ).encode(),
            json.dumps({"job_id": "batch"}).encode(),
            json.dumps(
                {
                    "status": "completed",
                    "artifacts": [
                        {
                            "index": 0,
                            "seed": 7,
                            "sha256": hashlib.sha256(generated).hexdigest(),
                        }
                    ],
                }
            ).encode(),
            generated,
        ]
    )

    def fake_request(*args, **kwargs):
        captured.append((args[2], kwargs))
        return next(replies)

    with (
        patch("audio_node_client._request", side_effect=fake_request),
        patch("audio_node_client._validate_wav"),
    ):
        render_batch(
            "http://192.168.88.52:8788",
            "x" * 32,
            payload={
                "prompt": "abstract reusable recipe",
                "batch_size": 1,
                "seeds": [7],
                "task_type": "cover",
                "reference_audio": str(reference),
            },
            out_dir=tmp_path / "batch",
        )

    assert captured[0][0] == "/v1/music-reference"
    submitted = captured[1][1]["body"]
    assert "reference_audio" not in submitted
    assert submitted["reference_audio_id"] == hashlib.sha256(raw_reference).hexdigest()
    assert str(reference) not in json.dumps(submitted)
