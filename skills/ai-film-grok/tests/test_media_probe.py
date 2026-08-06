from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from media_probe import MediaProbeError, run_media_command, run_media_to_output  # noqa: E402


def test_media_command_is_non_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    run_media_command(["ffprobe", "-v", "error"], timeout=3)
    assert "-nostdin" not in seen["argv"]
    assert seen["stdin"] is subprocess.DEVNULL
    assert seen["timeout"] == 3

    run_media_command(["ffmpeg", "-v", "error"], timeout=3)
    assert "-nostdin" in seen["argv"]


def test_media_command_timeout_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(MediaProbeError, match="ffmpeg timed out after 2s"):
        run_media_command(["ffmpeg"], timeout=2)


def test_media_output_failure_preserves_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "final.mp4"
    target.write_bytes(b"previous-final")

    def fake_run(argv, **kwargs):
        temp = Path(argv[-1])
        temp.write_bytes(b"partial")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="encoder failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(MediaProbeError, match="failed|empty|undersized"):
        run_media_to_output(["ffmpeg", "-y", str(target)], target, timeout=3)
    assert target.read_bytes() == b"previous-final"
    assert list(tmp_path.glob(".*.mp4")) == []


def test_media_output_publishes_only_after_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "final.mp4"

    def fake_run(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"new-final")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "media_probe.probe_media", lambda *_args, **_kwargs: {"format": {"duration": "1"}}
    )
    run_media_to_output(["ffmpeg", "-y", str(target)], target, timeout=3, min_bytes=1)
    assert target.read_bytes() == b"new-final"
