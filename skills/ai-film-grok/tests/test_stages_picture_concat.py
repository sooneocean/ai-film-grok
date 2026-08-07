"""Unit tests for final.stages_picture_concat (W1.6)."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from final.stages_picture_concat import make_title_end_cards


def test_make_title_end_cards_blank_no_text_draw(tmp_path: Path, monkeypatch) -> None:
    calls: list = []

    def fake_mkcard(text, out, **kw):
        calls.append((text, Path(out).name, kw.get("duration")))
        Path(out).write_bytes(b"x")

    import final.stages_picture_concat as m

    monkeypatch.setattr(m, "mkcard_video", fake_mkcard)
    args = SimpleNamespace(
        plate_cards="blank",
        title=None,
        end_title=None,
        title_dur=1.0,
        end_dur=0.5,
    )
    out = make_title_end_cards(
        args=args,
        spec={"title": "Film A"},
        manifest={},
        work=tmp_path,
        width=720,
        height=1280,
        fps=30,
        font_path="",
    )
    assert out["title_text"] == "Film A"
    assert out["title_dur"] == 1.0
    assert out["end_dur"] == 0.5
    # blank plates draw empty string
    assert calls[0][0] == ""
    assert calls[1][0] == ""


def test_exports() -> None:
    from final.stages_picture_concat import (
        assemble_picture_track,
        concat_picture_timeline,
        stretch_shot_plates,
    )

    assert callable(assemble_picture_track)
    assert callable(stretch_shot_plates)
    assert callable(concat_picture_timeline)
