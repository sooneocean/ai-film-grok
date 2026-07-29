from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lipsync_backend  # noqa: E402


def test_explicit_target_requires_speaker_face_and_near_shot() -> None:
    valid = {
        "lipsync": True,
        "speaker": "hero",
        "face_target": "hero",
        "dsl": {"camera": {"shot_size": "close-up", "angle": "front"}},
    }
    assert lipsync_backend.should_lipsync_shot(valid)
    assert not lipsync_backend.should_lipsync_shot({**valid, "speaker": ""})
    assert not lipsync_backend.should_lipsync_shot({**valid, "face_target": ""})
    assert not lipsync_backend.should_lipsync_shot(
        {**valid, "dsl": {"camera": {"shot_size": "wide", "angle": "front"}}}
    )
    assert not lipsync_backend.should_lipsync_shot(
        {
            **valid,
            "dsl": {"camera": {"shot_size": "documentary wide", "angle": "front"}},
        }
    )
    assert not lipsync_backend.should_lipsync_shot(
        {
            **valid,
            "dsl": {"camera": {"shot_size": "security camera wide", "angle": "front"}},
        }
    )
    assert not lipsync_backend.should_lipsync_shot(
        {**valid, "dsl": {"camera": {"shot_size": "close-up", "angle": "profile"}}}
    )
    assert not lipsync_backend.should_lipsync_shot(
        {
            **valid,
            "cast": ["hero", "partner"],
            "face_target": "",
        }
    )


def test_dialogue_render_forbids_lipsync_off() -> None:
    with pytest.raises(lipsync_backend.LipSyncError, match="--lipsync off is forbidden"):
        lipsync_backend.enforce_dialogue_lipsync(
            vo_mode="dialogue_drama",
            requested="off",
            shots=[{"id": "talk01", "screen_mode": "on_camera"}],
        )


def test_dialogue_auto_requires_a_ready_preservation_backend() -> None:
    with mock.patch.object(
        lipsync_backend, "resolve_backend", return_value="latentsync"
    ) as resolve:
        assert (
            lipsync_backend.enforce_dialogue_lipsync(
                vo_mode="dialogue_drama",
                requested="auto",
                shots=[{"id": "talk01", "screen_mode": "on_camera"}],
            )
            == "require"
        )
    resolve.assert_called_once_with("require")


def test_non_dialogue_render_keeps_lipsync_off() -> None:
    assert (
        lipsync_backend.enforce_dialogue_lipsync(
            vo_mode="storyteller",
            requested="off",
            shots=[{"id": "talk01", "screen_mode": "on_camera"}],
        )
        == "off"
    )


def test_node_latentsync_precedes_local_backends() -> None:
    cfg = mock.Mock(
        lipsync_backend="auto",
        lipsync_node_base_url="http://192.168.88.52:8790",
        lipsync_node_token="x" * 32,
        musetalk_root="",
        wav2lip_root="",
        lipsync_argv="",
    )
    node_health = {
        "ok": True,
        "backends": {
            "latentsync": {"ready": True},
            "musetalk": {"ready": True},
        },
    }
    with (
        mock.patch.object(lipsync_backend, "get_config", return_value=cfg),
        mock.patch("lipsync_node_client.health", return_value=node_health),
    ):
        info = lipsync_backend.probe()
        assert info["ready"][:2] == ["latentsync", "musetalk"]
        assert lipsync_backend.resolve_backend("auto") == "latentsync"


def test_unapproved_node_backend_is_not_in_auto_route() -> None:
    cfg = mock.Mock(
        lipsync_backend="auto",
        lipsync_node_base_url="http://127.0.0.1:18790",
        lipsync_node_token="x" * 32,
        musetalk_root="",
        wav2lip_root="",
        lipsync_argv="",
    )
    node_health = {
        "ok": True,
        "backends": {
            "latentsync": {"ready": False, "technical_ready": True, "approved": False},
            "musetalk": {"ready": False, "technical_ready": False, "approved": False},
        },
    }
    with (
        mock.patch.object(lipsync_backend, "get_config", return_value=cfg),
        mock.patch("lipsync_node_client.health", return_value=node_health),
    ):
        info = lipsync_backend.probe()
        assert "latentsync" not in info["ready"]


def test_unapproved_musetalk_is_not_sent_as_production_fallback(tmp_path: Path) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.wav"
    output = tmp_path / "output.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    cfg = mock.Mock(
        lipsync_node_base_url="http://127.0.0.1:18790",
        lipsync_node_token="x" * 32,
        lipsync_fallback="musetalk",
    )
    node_probe = {
        "node": {
            "backends": {
                "latentsync": {"ready": True, "technical_ready": True},
                "musetalk": {"ready": False, "technical_ready": True},
            }
        }
    }
    with (
        mock.patch.object(lipsync_backend, "probe", return_value=node_probe),
        mock.patch.object(lipsync_backend, "resolve_backend", return_value="latentsync"),
        mock.patch.object(lipsync_backend, "get_config", return_value=cfg),
        mock.patch("lipsync_node_client.render", return_value={"ok": True}) as render,
    ):
        lipsync_backend.lipsync_one(
            video=video,
            audio=audio,
            out=output,
            backend="latentsync",
        )

    assert render.call_args.kwargs["fallback_backend"] == ""


def test_pilot_can_explicitly_disable_global_node_fallback(tmp_path: Path) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.wav"
    output = tmp_path / "output.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    cfg = mock.Mock(
        lipsync_node_base_url="http://127.0.0.1:18790",
        lipsync_node_token="x" * 32,
        lipsync_fallback="musetalk",
    )
    node_probe = {
        "node": {
            "backends": {
                "latentsync": {"ready": True, "technical_ready": True},
                "musetalk": {"ready": True, "technical_ready": True},
            }
        }
    }
    with (
        mock.patch.object(lipsync_backend, "probe", return_value=node_probe),
        mock.patch.object(lipsync_backend, "resolve_backend", return_value="latentsync"),
        mock.patch.object(lipsync_backend, "get_config", return_value=cfg),
        mock.patch("lipsync_node_client.render", return_value={"ok": True}) as render,
    ):
        lipsync_backend.lipsync_one(
            video=video,
            audio=audio,
            out=output,
            backend="latentsync",
            allow_node_fallback=False,
        )

    assert render.call_args.kwargs["fallback_backend"] == ""
