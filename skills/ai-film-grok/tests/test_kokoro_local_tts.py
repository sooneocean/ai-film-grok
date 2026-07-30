from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ADAPTERS = SCRIPTS / "adapters"
sys.path.insert(0, str(ADAPTERS))
sys.path.insert(0, str(SCRIPTS))

kokoro_tts = importlib.import_module("kokoro_tts")
tts_backend = importlib.import_module("tts_backend")


def test_kokoro_rejects_edge_voice_identifier() -> None:
    with pytest.raises(kokoro_tts.KokoroError, match="provider-native"):
        kokoro_tts._voice("zh-CN-XiaoxiaoNeural")
    with pytest.raises(kokoro_tts.KokoroError, match="provider-native"):
        kokoro_tts._voice("en-US-JennyNeural")


def test_kokoro_uses_only_approved_local_model_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    assert kokoro_tts._offline_repo_id() == kokoro_tts.DEFAULT_REPO_ID
    assert os.environ["HF_HUB_OFFLINE"] == "1"

    monkeypatch.setenv("KOKORO_REPO_ID", "untrusted/model")
    with pytest.raises(kokoro_tts.KokoroError, match="approved Kokoro Chinese model"):
        kokoro_tts._offline_repo_id()


def test_kokoro_argv_detection_and_local_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SCRIPTS / "adapters" / "kokoro_tts.py"
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        f'["python3","{adapter}","--out","{{out}}"]',
    )
    monkeypatch.setenv("KOKORO_VOICE", "zf_001")

    assert tts_backend.kokoro_local_argv_configured()
    assert tts_backend.external_tts_timeout() == 600
    env = tts_backend.external_tts_subprocess_env()
    assert env["KOKORO_VOICE"] == "zf_001"


def test_explicit_kokoro_backend_requires_our_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_TTS_ARGV", '["python3","/trusted/other.py"]')
    with pytest.raises(tts_backend.TTSError, match="requires AIFILM_TTS_ARGV"):
        tts_backend.synthesize(
            "local only",
            tmp_path / "out.mp3",
            backend="kokoro-local",
            voice="zf_001",
        )
