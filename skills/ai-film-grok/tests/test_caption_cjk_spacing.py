"""Chinese caption spacing lint + auto-fix."""

from __future__ import annotations

from pathlib import Path

from caption_pixel_check import (
    fix_chinese_caption_srt,
    fix_chinese_caption_text,
    lint_chinese_caption_spacing,
)


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


def test_fix_text():
    assert fix_chinese_caption_text("你 好 啊") == "你好啊"
    assert fix_chinese_caption_text("OK 你好") == "OK 你好" or "你好" in fix_chinese_caption_text(
        "OK 你好"
    )


def test_fix_srt_file(tmp_path: Path):
    srt = tmp_path / "final.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\n你 好 啊\n\n",
        encoding="utf-8",
    )
    rep = fix_chinese_caption_srt(srt, write=True, backup=True)
    assert rep["fixed"] >= 1
    assert lint_chinese_caption_spacing(srt)["ok"] is True
    assert "你好啊" in srt.read_text(encoding="utf-8")
