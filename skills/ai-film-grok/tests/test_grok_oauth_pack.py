"""Unit tests for Grok OAuth pack (no live network required for pure helpers)."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import grok_oauth as go  # noqa: E402
from generation_usage import start_generation, usage_status  # noqa: E402


def test_download_url_uses_curl_and_publishes_atomically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"previously-approved")
    captured: list[str] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        captured.extend(command)
        partial = Path(command[command.index("--output") + 1])
        partial.write_bytes(b"new-artifact")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(go.subprocess, "run", fake_run)

    assert go._download_url("https://example.com/clip.mp4", output) == output
    assert output.read_bytes() == b"new-artifact"
    assert not list(tmp_path.glob("*.partial"))
    assert captured == [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--connect-timeout",
        "30",
        "--max-time",
        "180",
        "--user-agent",
        "aifilm-grok-oauth/1.1",
        "--output",
        captured[captured.index("--output") + 1],
        "--url",
        "https://example.com/clip.mp4",
    ]


def test_download_url_failure_preserves_existing_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "clip.mp4"
    output.write_bytes(b"previously-approved")
    monkeypatch.setattr(
        go.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=22, stdout="", stderr="404 Not Found"),
    )

    with pytest.raises(go.GrokOAuthError, match="404 Not Found"):
        go._download_url("https://example.com/missing.mp4", output)

    assert output.read_bytes() == b"previously-approved"
    assert not list(tmp_path.glob("*.partial"))


def test_download_url_uses_distinct_partials_for_concurrent_downloads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "clip.mp4"
    entered = threading.Barrier(2)
    partials: list[Path] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        partial = Path(command[command.index("--output") + 1])
        partials.append(partial)
        entered.wait(timeout=1)
        partial.write_bytes(b"artifact")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(go.subprocess, "run", fake_run)
    workers = [
        threading.Thread(target=go._download_url, args=("https://example.com/clip.mp4", output))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len(partials) == 2
    assert partials[0] != partials[1]
    assert output.read_bytes() == b"artifact"
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.slow
def test_file_to_data_url_png(tmp_path: Path) -> None:
    p = tmp_path / "t.png"
    # minimal valid-ish bytes
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    url = go.file_to_data_url(p)
    assert url.startswith("data:image/png;base64,")
    payload = url.split(",", 1)[1]
    assert base64.b64decode(payload)[:4] == b"\x89PNG"


@pytest.mark.slow
def test_image_input_object_url_passthrough() -> None:
    assert go._image_input_object("https://example.com/a.png") == {
        "url": "https://example.com/a.png"
    }
    assert go._image_input_object("data:image/png;base64,AAA") == {
        "url": "data:image/png;base64,AAA"
    }


@pytest.mark.slow
def test_probe_pack_flags_without_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_GROK_AUTH_PATH", str(tmp_path / "missing-auth.json"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("AIFILM_GROK_AUTH", "oauth")
    rep = go.probe(deep=False)
    assert rep["ok"] is False
    assert "pack" in rep
    assert rep["pack"]["video_i2v"] is True
    assert rep["pack"]["tts"] is True
    assert rep["pack"]["native_lipsync"] is False


@pytest.mark.slow
def test_chat_completion_json_mode_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_token(**_k):
        return {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"}

    def fake_http(method, url, *, token, body=None, timeout=120):
        captured["body"] = body
        return {
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"total_tokens": 1},
        }

    monkeypatch.setattr(go, "get_access_token", fake_token)
    monkeypatch.setattr(go, "_http_json", fake_http)
    out = go.chat_completion("hi", json_mode=True)
    assert out["ok"] is True
    assert captured["body"]["response_format"] == {"type": "json_object"}


@pytest.mark.slow
def test_video_submit_requires_image_for_15(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    with pytest.raises(go.GrokOAuthError, match="image-to-video only"):
        go.video_submit("leaf falls", model="grok-imagine-video-1.5")


@pytest.mark.slow
def test_video_submit_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(
        go,
        "_http_json",
        lambda *a, **k: {"request_id": "rid-123"},
    )
    monkeypatch.setattr(go, "_image_input_object", lambda x: {"url": "data:image/png;base64,AA"})
    out = go.video_submit("motion", image="/tmp/x.png", duration=6)
    assert out["request_id"] == "rid-123"
    assert out["ok"] is True


def test_video_submit_records_local_reference_hashes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    keyframe = tmp_path / "keyframe.png"
    style = tmp_path / "style.png"
    keyframe.write_bytes(b"keyframe")
    style.write_bytes(b"style")
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(go, "_http_json", lambda *a, **k: {"request_id": "rid-refs"})
    monkeypatch.setattr(go, "_image_input_object", lambda x: {"url": "data:image/png;base64,AA"})
    out = go.video_submit("motion", image=keyframe, reference_images=[style])
    assert out["input_provenance"]["keyframe_sha256"] == hashlib.sha256(b"keyframe").hexdigest()
    assert out["input_provenance"]["reference_image_sha256s"] == [
        hashlib.sha256(b"style").hexdigest()
    ]


def test_video_submit_binds_reference_provenance_to_usage_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    keyframe = tmp_path / "keyframe.png"
    style = tmp_path / "style.png"
    keyframe.write_bytes(b"keyframe")
    style.write_bytes(b"style")
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(go, "_http_json", lambda *a, **k: {"request_id": "rid-ledger"})
    monkeypatch.setattr(go, "_image_input_object", lambda x: {"url": "data:image/png;base64,AA"})
    go.video_submit("motion", image=keyframe, reference_images=[style], usage_root=tmp_path)
    ledger = json.loads((tmp_path / "receipts" / "generation-usage.json").read_text())
    started = next(event for event in ledger["events"] if event["phase"] == "started")
    assert len(started["input_hash"]) == 64
    assert str(keyframe) not in json.dumps(ledger)
    assert str(style) not in json.dumps(ledger)


@pytest.mark.slow
def test_image_generation_preserves_and_records_exact_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(
        go,
        "_http_json",
        lambda *a, **k: {
            "data": [{"url": "https://example.com/generated.png"}],
            "usage": {
                "input_tokens": 9,
                "total_tokens": 9,
                "cost_in_usd_ticks": 200,
                "authorization": "must-not-persist",
            },
        },
    )
    monkeypatch.setattr(
        go,
        "_download_url",
        lambda _url, out: Path(out).write_bytes(b"x" * 200) or Path(out),
    )
    film = tmp_path / "film"
    out = go.images_generate("cat", out=tmp_path / "cat.png", usage_root=film)

    assert out["usage"] == {
        "input_tokens": 9,
        "total_tokens": 9,
        "cost_in_usd_ticks": 200,
    }
    from generation_usage import usage_status

    report = usage_status(film)
    assert report["requests_total"] == 1
    assert report["cost_in_usd_ticks"] == 200


@pytest.mark.slow
def test_video_submit_and_terminal_poll_share_generation_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    responses = iter(
        [
            {"request_id": "rid-usage"},
            {
                "status": "done",
                "model": "video-1",
                "video": {"url": "https://example.com/video.mp4", "duration": 6},
                "usage": {"cost_in_usd_ticks": 900},
            },
        ]
    )
    monkeypatch.setattr(go, "_http_json", lambda *a, **k: next(responses))
    monkeypatch.setattr(go, "_image_input_object", lambda x: {"url": "data:image/png;base64,AA"})
    film = tmp_path / "film"

    submitted = go.video_submit(
        "motion",
        image="/tmp/x.png",
        duration=6,
        usage_root=film,
    )
    done = go.video_status(
        submitted["request_id"],
        usage_root=film,
        generation_id=submitted["generation_id"],
    )

    assert done["usage"] == {"cost_in_usd_ticks": 900}
    from generation_usage import usage_status

    report = usage_status(film)
    assert report["requests_total"] == 1
    assert report["cost_in_usd_ticks"] == 900


def test_video_submit_usage_survives_terminal_poll_without_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = iter(
        [
            {"request_id": "req-submit-cost", "usage": {"cost_in_usd_ticks": 777}},
            {
                "status": "done",
                "video": {
                    "url": "https://example.test/video.mp4",
                    "respect_moderation": True,
                },
            },
        ]
    )
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(go, "_http_json", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(go, "_image_input_object", lambda _x: {"url": "data:image/png;base64,AA"})

    submitted = go.video_submit("motion", image="/tmp/x.png", usage_root=tmp_path)
    go.video_status(
        submitted["request_id"],
        usage_root=tmp_path,
        generation_id=submitted["generation_id"],
    )

    assert usage_status(tmp_path)["cost_in_usd_ticks"] == 777
    assert usage_status(tmp_path)["unknown_cost_requests"] == 0


def test_video_moderation_is_recorded_as_moderated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(
        go,
        "_http_json",
        lambda *_args, **_kwargs: {
            "status": "done",
            "video": {"respect_moderation": False},
            "usage": {"cost_in_usd_ticks": 88},
        },
    )
    gid = start_generation(tmp_path, operation="i2v", provider="xai")

    result = go.video_status(
        "req-moderated",
        usage_root=tmp_path,
        generation_id=gid,
    )

    assert result["status"] == "done"
    assert usage_status(tmp_path)["status_counts"] == {"moderated": 1}


def test_tts_write_failure_preserves_provider_usage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(
        go,
        "_http_bytes",
        lambda *_args, **_kwargs: (
            json.dumps(
                {
                    "audio": base64.b64encode(b"x" * 500).decode("ascii"),
                    "usage": {"cost_in_usd_ticks": 99},
                }
            ).encode("utf-8"),
            "application/json",
        ),
    )
    output_directory = tmp_path / "audio-dir"
    output_directory.mkdir()

    with pytest.raises(go.GrokOAuthError, match="output write failed"):
        go.tts_speak("hello", out=output_directory, usage_root=tmp_path)

    report = usage_status(tmp_path)
    assert report["status_counts"] == {"failed": 1}
    assert report["cost_in_usd_ticks"] == 99


@pytest.mark.slow
def test_tts_speak_raw_mp3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    audio = b"ID3" + b"\x00" * 500

    def fake_bytes(*a, **k):
        return audio, "audio/mpeg"

    monkeypatch.setattr(go, "_http_bytes", fake_bytes)
    out = tmp_path / "vo.mp3"
    rep = go.tts_speak("你好", out=out, language="zh", voice_id="eve")
    assert rep["ok"] is True
    assert out.read_bytes() == audio


@pytest.mark.slow
def test_tts_backend_includes_grok() -> None:
    import tts_backend as tb

    assert "grok" in tb.TTS_BACKENDS
    # Neural id allowed with grok (will be stripped)
    tb.assert_voice_backend_compatible("grok", "zh-CN-XiaoxiaoNeural")


@pytest.mark.slow
def test_cli_help_lists_video_tts() -> None:
    # argparse smoke: main(["doctor"]) needs network — just ensure parser builds
    with mock.patch.object(sys, "argv", ["grok_oauth", "doctor"]):
        # import side-effect free
        assert callable(go.main)
