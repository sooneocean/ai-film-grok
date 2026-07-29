from __future__ import annotations

import base64
import sys
from pathlib import Path, PureWindowsPath

import pytest

ADAPTERS = Path(__file__).resolve().parents[1] / "scripts" / "adapters"
sys.path.insert(0, str(ADAPTERS))

import vibevoice_asr_ssh  # noqa: E402


@pytest.mark.parametrize("target", ["-oProxyCommand=evil", "user@host;evil", "user@host host"])
def test_rejects_unsafe_ssh_target(monkeypatch: pytest.MonkeyPatch, target: str) -> None:
    monkeypatch.setenv("AIFILM_VIBEVOICE_ASR_SSH_TARGET", target)
    with pytest.raises(vibevoice_asr_ssh.RemoteASRError, match="safe SSH destination"):
        vibevoice_asr_ssh._ssh_target()


def test_accepts_windows_domain_ssh_target(monkeypatch: pytest.MonkeyPatch) -> None:
    target = r"DESKTOP-QFKIQD9\\user@192.168.30.36"
    monkeypatch.setenv("AIFILM_VIBEVOICE_ASR_SSH_TARGET", target)
    assert vibevoice_asr_ssh._ssh_target() == target


@pytest.mark.parametrize(
    ("value", "root"),
    [
        (r"C:\\aifilm-vibevoice\\..\\other", vibevoice_asr_ssh._REMOTE_ROOT),
        (r"D:\\aifilm-vibevoice", vibevoice_asr_ssh._REMOTE_ROOT),
        (r"C:\\other", vibevoice_asr_ssh._REMOTE_MODEL_ROOT),
    ],
)
def test_rejects_remote_path_outside_allowlist(value: str, root: PureWindowsPath) -> None:
    with pytest.raises(vibevoice_asr_ssh.RemoteASRError, match="below"):
        vibevoice_asr_ssh._windows_path(value, allowed_root=root, name="remote path")


def test_quotes_powershell_single_quotes() -> None:
    assert vibevoice_asr_ssh._ps_quote("a'b") == "'a''b'"


def test_cleanup_is_token_scoped_and_uses_literal_paths() -> None:
    command = vibevoice_asr_ssh._cleanup_command(
        options=["-o", "StrictHostKeyChecking=yes"],
        target="user@192.168.30.36",
        remote_audio=r"C:\\aifilm-vibevoice\\jobs\\token.wav",
        remote_out=r"C:\\aifilm-vibevoice\\jobs\\token.json",
    )
    script = base64.b64decode(command[-1]).decode("utf-16le")
    assert command[:5] == ["ssh", "-o", "StrictHostKeyChecking=yes", "--", "user@192.168.30.36"]
    assert "Remove-Item -LiteralPath" in script
    assert "token.wav" in script and "token.json" in script


def test_ssh_options_accepts_legacy_hostkey_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "id_ed25519"
    key.write_text("test", encoding="utf-8")
    monkeypatch.setenv("AIFILM_VIBEVOICE_ASR_SSH_KEY", str(key))
    monkeypatch.delenv("AIFILM_VIBEVOICE_ASR_SSH_HOSTKEY_ALIAS", raising=False)
    monkeypatch.setenv("AIFILM_VIBEVOICE_ASR_SSH_HOSTKEY", "private-5090")

    options = vibevoice_asr_ssh._ssh_options()

    assert "HostKeyAlias=private-5090" in options
