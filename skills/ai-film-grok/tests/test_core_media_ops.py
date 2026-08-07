"""C6.4 base contracts for core.media_ops pure parsers + injectible probe."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.media_ops import (  # noqa: E402
    parse_max_volume_db,
    parse_mean_volume_db,
    parse_volume_stats,
    probe_native_audio_mean_volume,
    probe_volume_stats,
)


SAMPLE_LOG = """
[Parsed_volumedetect_0 @ 0x] n_samples: 48000
[Parsed_volumedetect_0 @ 0x] mean_volume: -18.5 dB
[Parsed_volumedetect_0 @ 0x] max_volume: -3.25 dB
"""


def test_parse_mean_volume_db_ok() -> None:
    assert parse_mean_volume_db(SAMPLE_LOG) == pytest.approx(-18.5)


def test_parse_max_volume_db_ok() -> None:
    assert parse_max_volume_db(SAMPLE_LOG) == pytest.approx(-3.25)


def test_parse_volume_stats_both() -> None:
    stats = parse_volume_stats(SAMPLE_LOG)
    assert stats["mean_volume_db"] == pytest.approx(-18.5)
    assert stats["max_volume_db"] == pytest.approx(-3.25)
    assert "mean_volume" in (stats.get("raw_text") or "")


def test_parse_volume_missing_returns_none() -> None:
    assert parse_mean_volume_db("") is None
    assert parse_max_volume_db("no volume line") is None
    empty = parse_volume_stats("noise only")
    assert empty["mean_volume_db"] is None
    assert empty["max_volume_db"] is None


def test_probe_volume_stats_uses_run_fn(tmp_path: Path) -> None:
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"x")

    def run_fn(cmd, check=False, timeout=None):  # noqa: ANN001
        return SimpleNamespace(stdout="", stderr=SAMPLE_LOG)

    stats = probe_volume_stats(fake, run_fn=run_fn)
    assert stats["mean_volume_db"] == pytest.approx(-18.5)


def test_probe_native_audio_mean_volume_run_fn(tmp_path: Path) -> None:
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"x")

    def run_fn(cmd, check=False, timeout=None):  # noqa: ANN001
        return SimpleNamespace(stdout=SAMPLE_LOG, stderr="")

    mean = probe_native_audio_mean_volume(fake, run_fn=run_fn)
    assert mean == pytest.approx(-18.5)


def test_probe_volume_stats_runner_oserror_returns_empty(tmp_path: Path) -> None:
    fake = tmp_path / "clip.mp4"
    fake.write_bytes(b"x")

    def run_fn(cmd, check=False, timeout=None):  # noqa: ANN001
        raise OSError("ffmpeg missing")

    stats = probe_volume_stats(fake, run_fn=run_fn)
    assert stats["mean_volume_db"] is None
    assert stats["max_volume_db"] is None
