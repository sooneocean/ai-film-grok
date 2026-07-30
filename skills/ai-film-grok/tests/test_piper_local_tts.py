from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "adapters"))
sys.path.insert(0, str(SCRIPTS))

piper = importlib.import_module("piper_local_tts")
tts_backend = importlib.import_module("tts_backend")


def test_piper_accepts_only_the_approved_voice() -> None:
    assert piper._voice("") == "zh_CN-chaowen-medium"
    with pytest.raises(piper.PiperError, match="approved"):
        piper._voice("zh-CN-XiaoxiaoNeural")


def test_piper_requires_fixed_adapter_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SCRIPTS / "adapters" / "piper_local_tts.py"
    runtime = SCRIPTS.parents[2] / ".local-runtimes" / "piper-mac" / "bin" / "python"
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        f'["{runtime}","{adapter}","--text-file","{{text_file}}","--out","{{out}}","--voice","{{voice}}"]',
    )
    assert tts_backend.piper_local_argv_configured()
    assert tts_backend.external_tts_timeout() == 600
