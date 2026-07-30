from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "adapters"))
sys.path.insert(0, str(SCRIPTS))

chatterbox = importlib.import_module("chatterbox_local_tts")
tts_backend = importlib.import_module("tts_backend")


def _configured_argv(adapter: Path) -> str:
    interpreter = SCRIPTS.parents[2] / ".local-runtimes" / "chatterbox-mac" / "bin" / "python"
    return (
        f'["{interpreter}","{adapter}","--text-file","{{text_file}}",'
        '"--out","{out}","--voice","{voice}"]'
    )


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
    monkeypatch.setenv("AIFILM_TTS_ARGV", _configured_argv(adapter))
    monkeypatch.setenv("CHATTERBOX_LANGUAGE", "ja")
    assert tts_backend.chatterbox_local_argv_configured()
    assert tts_backend.external_tts_timeout() == 600
    assert tts_backend.external_tts_subprocess_env()["CHATTERBOX_LANGUAGE"] == "ja"


def test_chatterbox_rejects_argv_trust_bypasses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adapter = SCRIPTS / "adapters" / "chatterbox_local_tts.py"
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        f'["/bin/sh","{adapter}","--text-file","{{text_file}}","--out","{{out}}"]',
    )
    assert not tts_backend.chatterbox_local_argv_configured()
    fake_python = tmp_path / "python"
    fake_python.symlink_to("/bin/sh")
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        f'["{fake_python}","{adapter}","--text-file","{{text_file}}","--out","{{out}}"]',
    )
    assert not tts_backend.chatterbox_local_argv_configured()
    monkeypatch.setenv(
        "AIFILM_TTS_ARGV",
        _configured_argv(adapter)[:-1] + ',"--out","/tmp/overwrite"]',
    )
    assert not tts_backend.chatterbox_local_argv_configured()


def test_chatterbox_errors_do_not_echo_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "synthetic-secret-must-not-leak"

    class FailingModel:
        @classmethod
        def from_pretrained(cls, **kwargs: object) -> object:
            del cls, kwargs
            raise RuntimeError(secret)

    torch = SimpleNamespace(
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        cuda=SimpleNamespace(is_available=lambda: False),
    )
    package = ModuleType("chatterbox")
    package.__path__ = []  # type: ignore[attr-defined]
    module = ModuleType("chatterbox.mtl_tts")
    module.ChatterboxMultilingualTTS = FailingModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "torchaudio", ModuleType("torchaudio"))
    monkeypatch.setitem(sys.modules, "chatterbox", package)
    monkeypatch.setitem(sys.modules, "chatterbox.mtl_tts", module)
    with pytest.raises(chatterbox.ChatterboxError) as model_error:
        chatterbox.synthesize("safe text", tmp_path / "unused.mp3")
    assert secret not in str(model_error.value)

    adapter = SCRIPTS / "adapters" / "chatterbox_local_tts.py"
    monkeypatch.setenv("AIFILM_TTS_ARGV", _configured_argv(adapter))
    monkeypatch.setattr(
        tts_backend.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=secret, stdout=""),
    )
    with pytest.raises(tts_backend.TTSError) as process_error:
        tts_backend.tts_external("safe text", tmp_path / "out.mp3")
    assert secret not in str(process_error.value)


def test_chatterbox_output_rejects_symlink_components(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "render.mp3"
    source.write_bytes(b"x" * 600)
    with pytest.raises(chatterbox.ChatterboxError, match="symbolic link"):
        chatterbox._install_output(source, workspace / "linked" / "out.mp3")
    assert not (outside / "out.mp3").exists()

    adapter = SCRIPTS / "adapters" / "chatterbox_local_tts.py"
    monkeypatch.setenv("AIFILM_TTS_ARGV", _configured_argv(adapter))
    monkeypatch.setattr(
        tts_backend.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="", stdout=""),
    )
    with pytest.raises(tts_backend.TTSError, match="CHATTERBOX_LOCAL_PROCESS_FAILED"):
        tts_backend.tts_external("private dialogue", workspace / "linked" / "out.mp3")
    assert not (outside / "out.txt").exists()

    victim = outside / "victim.mp3"
    victim.write_bytes(b"original")
    target = workspace / "out.mp3"
    target.symlink_to(victim)
    source.write_bytes(b"x" * 600)
    with pytest.raises(chatterbox.ChatterboxError, match="symbolic link"):
        chatterbox._install_output(source, target)
    assert victim.read_bytes() == b"original"


def test_chatterbox_backend_requires_our_adapter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIFILM_TTS_ARGV", '["python3","/trusted/other.py"]')
    with pytest.raises(tts_backend.TTSError, match="requires AIFILM_TTS_ARGV"):
        tts_backend.synthesize("local only", tmp_path / "out.mp3", backend="chatterbox-local")
