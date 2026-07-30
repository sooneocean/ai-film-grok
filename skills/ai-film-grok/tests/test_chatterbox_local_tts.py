from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "adapters"))
sys.path.insert(0, str(SCRIPTS))

chatterbox = importlib.import_module("chatterbox_local_tts")
tts_backend = importlib.import_module("tts_backend")


def test_chatterbox_rejects_edge_voice_and_unknown_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(chatterbox.ChatterboxError, match="provider-native"):
        chatterbox._voice("zh-CN-XiaoxiaoNeural")
    monkeypatch.setenv("CHATTERBOX_LANGUAGE", "fr")
    with pytest.raises(chatterbox.ChatterboxError, match="zh or ja"):
        chatterbox._language()


def test_chatterbox_argv_detection_and_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SCRIPTS / "adapters" / "chatterbox_local_tts.py"
    monkeypatch.setenv("AIFILM_TTS_ARGV", f'["python3","{adapter}","--out","{{out}}"]')
    monkeypatch.setenv("CHATTERBOX_LANGUAGE", "ja")
    assert tts_backend.chatterbox_local_argv_configured()
    assert tts_backend.external_tts_timeout() == 600
    assert tts_backend.external_tts_subprocess_env()["CHATTERBOX_LANGUAGE"] == "ja"


def test_chatterbox_backend_requires_our_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_TTS_ARGV", '["python3","/trusted/other.py"]')
    with pytest.raises(tts_backend.TTSError, match="requires AIFILM_TTS_ARGV"):
        tts_backend.synthesize("local only", tmp_path / "out.mp3", backend="chatterbox-local")
