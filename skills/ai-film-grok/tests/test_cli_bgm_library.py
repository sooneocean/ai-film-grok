from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import config_loader
import pytest
from cli_bgm_library import BGMLibraryError, _node_credentials, cmd_bgm_library


def test_node_credentials_loads_private_config_env_before_reading_environment(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        "AIFILM_AUDIO_NODE_URL=http://192.168.88.52:8788\n"
        "AIFILM_AUDIO_NODE_TOKEN=local-test-token-which-is-not-real\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_loader, "_SKILL_ROOT_CANDIDATES", [config])
    monkeypatch.setattr(config_loader, "_CONFIG", None)
    monkeypatch.setattr(config_loader, "_CONFIG_ENV_FINGERPRINT", None)
    monkeypatch.delenv("AIFILM_AUDIO_NODE_URL", raising=False)
    monkeypatch.delenv("AIFILM_AUDIO_NODE_TOKEN", raising=False)

    base, token = _node_credentials()

    assert base == "http://192.168.88.52:8788"
    assert token == "local-test-token-which-is-not-real"


def test_node_credentials_keep_explicit_environment_over_config(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.env"
    config.write_text(
        "AIFILM_AUDIO_NODE_URL=http://file-node\n"
        "AIFILM_AUDIO_NODE_TOKEN=file-token-which-is-not-real\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_loader, "_SKILL_ROOT_CANDIDATES", [config])
    monkeypatch.setattr(config_loader, "_CONFIG", None)
    monkeypatch.setattr(config_loader, "_CONFIG_ENV_FINGERPRINT", None)
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://env-node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "env-token-which-is-not-real")

    assert _node_credentials() == ("http://env-node", "env-token-which-is-not-real")


def test_node_credentials_fail_closed_when_configuration_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(config_loader, "_SKILL_ROOT_CANDIDATES", [])
    monkeypatch.setattr(config_loader, "_CONFIG", None)
    monkeypatch.setattr(config_loader, "_CONFIG_ENV_FINGERPRINT", None)
    monkeypatch.delenv("AIFILM_AUDIO_NODE_URL", raising=False)
    monkeypatch.delenv("AIFILM_AUDIO_NODE_TOKEN", raising=False)

    with pytest.raises(BGMLibraryError, match="required"):
        _node_credentials()


def test_doctor_projects_only_public_node_health_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "local-test-token-which-is-not-real")
    emitted: list[dict[str, object]] = []
    args = argparse.Namespace(bgm_library_action="doctor", library_root=str(tmp_path / "library"))
    health_report = {
        "ok": True,
        "node": "private-lan",
        "models": {"tts": True, "music": True, "secret": "another-secret"},
        "music_batch": True,
        "model": "local-test-token-which-is-not-real",
        "music_model": "ACE-Step-1.5",
        "music_checkpoint_fingerprint": "unknown",
        "gpu": {"name": "RTX 5090", "access_token": "doctor-raw-token-present"},
        "items": [{"api_key": "another-secret", "music": True}],
        "diagnostic": {"value": "unknown-field-secret"},
    }

    with patch("audio_node_client.health", return_value=health_report):
        assert cmd_bgm_library(args, emit=emitted.append) == 0

    serialized = repr(emitted)
    assert "doctor-raw-token-present" not in serialized
    assert "another-secret" not in serialized
    assert "unknown-field-secret" not in serialized
    assert emitted[0]["node"] == {
        "ok": True,
        "node": "private-lan",
        "models": {"tts": True, "music": True},
        "music_batch": True,
        "music_model": "ACE-Step-1.5",
        "music_checkpoint_fingerprint": "unknown",
        "gpu": {"name": "RTX 5090"},
    }


def test_doctor_uses_fixed_error_for_untrusted_health_exception(
    monkeypatch, tmp_path: Path
) -> None:
    token = "local-test-token-which-is-not-real"
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://node")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", token)
    emitted: list[dict[str, object]] = []
    args = argparse.Namespace(bgm_library_action="doctor", library_root=str(tmp_path / "library"))

    with patch("audio_node_client.health", side_effect=ValueError(token)):
        assert cmd_bgm_library(args, emit=emitted.append) == 0

    assert token not in repr(emitted)
    assert emitted[0]["node"] == {"ok": False, "error": "audio node health check failed"}
