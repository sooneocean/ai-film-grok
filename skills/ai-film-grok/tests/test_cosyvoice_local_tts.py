from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ADAPTERS = SCRIPTS / "adapters"
sys.path.insert(0, str(ADAPTERS))
sys.path.insert(0, str(SCRIPTS))

cosyvoice_local_tts = importlib.import_module("cosyvoice_local_tts")
tts_backend = importlib.import_module("tts_backend")


def test_cosyvoice_requires_complete_local_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "COSYVOICE_ROOT",
        "COSYVOICE_MODEL_DIR",
        "COSYVOICE_REF_WAV",
        "COSYVOICE_PROMPT_TEXT",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(cosyvoice_local_tts.CosyVoiceLocalError, match="all required"):
        cosyvoice_local_tts._configuration()


def test_cosyvoice_validates_checkout_model_and_regular_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "CosyVoice"
    (root / "cosyvoice").mkdir(parents=True)
    (root / "third_party" / "Matcha-TTS").mkdir(parents=True)
    model = tmp_path / "model"
    model.mkdir()
    (model / "cosyvoice3.yaml").write_text("sample_rate: 24000\n", encoding="utf-8")
    reference = tmp_path / "licensed.wav"
    reference.write_bytes(b"RIFF")
    monkeypatch.setenv("COSYVOICE_ROOT", str(root))
    monkeypatch.setenv("COSYVOICE_MODEL_DIR", str(model))
    monkeypatch.setenv("COSYVOICE_REF_WAV", str(reference))
    monkeypatch.setenv("COSYVOICE_PROMPT_TEXT", "authorized reference transcript")

    configured = cosyvoice_local_tts._configuration()

    assert configured[:3] == (root.resolve(), model.resolve(), reference.resolve())
    assert configured[3] == "authorized reference transcript"


def test_cosyvoice_rejects_edge_voice_identifier() -> None:
    with pytest.raises(cosyvoice_local_tts.CosyVoiceLocalError, match="provider-native"):
        cosyvoice_local_tts._provider_voice("zh-CN-XiaoxiaoNeural")


def test_explicit_cosyvoice_backend_requires_our_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_TTS_ARGV", '["python3","/trusted/other.py"]')
    with pytest.raises(tts_backend.TTSError, match="requires AIFILM_TTS_ARGV"):
        tts_backend.synthesize(
            "local only",
            tmp_path / "out.mp3",
            backend="cosyvoice-local",
            voice="cosyvoice-narrator",
        )


def test_cosyvoice_argv_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        '["python3","/trusted/adapters/cosyvoice_local_tts.py","--out","{out}"]',
    )
    assert tts_backend.cosyvoice_local_argv_configured()


def test_cosyvoice_local_settings_are_not_passed_to_other_external_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COSYVOICE_ROOT", "/private/cosy")
    monkeypatch.setenv("AIFILM_TTS_ARGV", '["python3","/trusted/other.py"]')
    assert "COSYVOICE_ROOT" not in tts_backend.external_tts_subprocess_env()
