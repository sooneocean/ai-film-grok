from __future__ import annotations

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
