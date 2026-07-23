from __future__ import annotations

import subprocess
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_probe import MediaProbeError, run_media_command  # noqa: E402


def test_media_command_is_non_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_media_command(["ffprobe", "-v", "error"], timeout=3)
    assert "-nostdin" in seen["argv"]
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["timeout"] == 3


def test_media_command_timeout_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(MediaProbeError, match="ffmpeg timed out after 2s"):
        run_media_command(["ffmpeg"], timeout=2)
