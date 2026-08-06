"""Chinese caption spacing lint."""

from __future__ import annotations

from pathlib import Path

from caption_pixel_check import lint_chinese_caption_spacing


def test_cjk_space_detected(tmp_path: Path):
    srt = tmp_path / "final.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n你 好 啊\n\n",
        encoding="utf-8",
    )
    rep = lint_chinese_caption_spacing(srt)
    assert rep["ok"] is False
    assert any(i["code"] == "CAPTION_CJK_INTERNAL_SPACE" for i in rep["issues"])


def test_cjk_clean_ok(tmp_path: Path):
    srt = tmp_path / "final.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n你好啊\n\n",
        encoding="utf-8",
    )
    rep = lint_chinese_caption_spacing(srt)
    assert rep["ok"] is True
