"""caption_pixel_check — bowl has soup (bottom-band heuristic)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from caption_pixel_check import (  # noqa: E402
    CaptionPixelError,
    assert_caption_pixels_for_closeout,
    caption_pixel_status,
    evidence_stale_after_final,
    run_caption_pixel_check,
)


def _write_minimal_mp4(path: Path) -> None:
    """Tiny fake file — probe is mocked; only path/hash matter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)


def _write_srt(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n你好\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n世界\n",
        encoding="utf-8",
    )


def test_skip_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_SKIP_CAPTION_PIXEL", "1")
    report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is True
    assert report["skipped"] is True
    st = caption_pixel_status(tmp_path)
    assert st["ok"] is True


def test_missing_final_is_red(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_SKIP_CAPTION_PIXEL", raising=False)
    report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is False
    assert report["missing_ink"] is True


def test_probe_ok_writes_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_SKIP_CAPTION_PIXEL", raising=False)
    final = tmp_path / "out" / "film_final.mp4"
    srt = tmp_path / "out" / "final.srt"
    _write_minimal_mp4(final)
    _write_srt(srt)
    with mock.patch(
        "final_stages.sample_bottom_band_activity",
        return_value={
            "ok": True,
            "likely_count": 2,
            "sample_count": 2,
            "samples": [
                {"ts": 1.5, "likely_caption_bar": True, "contrast": 40, "mean": 20, "ok": True},
                {"ts": 3.5, "likely_caption_bar": True, "contrast": 42, "mean": 22, "ok": True},
            ],
        },
    ):
        report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is True
    assert report["missing_ink"] is False
    st = caption_pixel_status(tmp_path)
    assert st["ok"] is True
    assert st["present"] is True


def test_probe_missing_ink_hard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_SKIP_CAPTION_PIXEL", raising=False)
    final = tmp_path / "out" / "film_final.mp4"
    srt = tmp_path / "out" / "final.srt"
    _write_minimal_mp4(final)
    _write_srt(srt)
    with mock.patch(
        "final_stages.sample_bottom_band_activity",
        return_value={"ok": False, "likely_count": 0, "sample_count": 2, "samples": []},
    ):
        report = run_caption_pixel_check(tmp_path, write=True)
    assert report["ok"] is False
    assert report["missing_ink"] is True
    with pytest.raises(CaptionPixelError):
        assert_caption_pixels_for_closeout(tmp_path, write_if_missing=False)


def test_stale_after_final_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_SKIP_CAPTION_PIXEL", raising=False)
    final = tmp_path / "out" / "film_final.mp4"
    srt = tmp_path / "out" / "final.srt"
    _write_minimal_mp4(final)
    _write_srt(srt)
    with mock.patch(
        "final_stages.sample_bottom_band_activity",
        return_value={"ok": True, "likely_count": 2, "sample_count": 2, "samples": []},
    ):
        run_caption_pixel_check(tmp_path, write=True)
    # rewrite final → stale
    final.write_bytes(final.read_bytes() + b"\xff")
    st = caption_pixel_status(tmp_path)
    assert st["stale"] is True
    assert st["ok"] is False
    ev = evidence_stale_after_final(tmp_path)
    assert any(i.get("code") == "CAPTION_PIXEL_STALE" for i in ev["issues"])


def test_quality_report_stale(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    _write_minimal_mp4(final)
    (tmp_path / "out" / "quality-report.json").write_text(
        json.dumps({"media_sha256": "deadbeef"}),
        encoding="utf-8",
    )
    ev = evidence_stale_after_final(tmp_path)
    assert any(i.get("code") == "QUALITY_REPORT_STALE" for i in ev["issues"])
