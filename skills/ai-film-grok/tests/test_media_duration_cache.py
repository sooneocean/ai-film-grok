"""Tests for optional ffprobe duration caching."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import media_duration


def test_duration_cache_avoids_second_probe(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media")
    report = {"format": {"duration": "2.5"}}
    with patch.object(media_duration, "probe_media", return_value=report) as probe:
        assert media_duration.probe_duration_sec(source, cache_root=tmp_path) == 2.5
        assert media_duration.probe_duration_sec(source, cache_root=tmp_path) == 2.5
    probe.assert_called_once()


def test_cache_does_not_hide_changed_media(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"media-v1")
    with patch.object(
        media_duration, "probe_media", return_value={"format": {"duration": "2.5"}}
    ) as probe:
        media_duration.probe_duration_sec(source, cache_root=tmp_path)
        source.write_bytes(b"media-v2")
        media_duration.probe_duration_sec(source, cache_root=tmp_path)
    assert probe.call_count == 2
