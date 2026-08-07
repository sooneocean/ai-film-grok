"""Unit tests for final.stages_subs (W1.4)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from final.stages_subs import burn_or_copy_subs, write_final_srt


def test_write_final_srt_creates_file(tmp_path: Path) -> None:
    class Err(Exception):
        pass

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    cues = [{"start": 0.0, "end": 1.0, "text": "你好"}]
    srt_path, srt_stable = write_final_srt(
        out_dir=out_dir,
        cues=cues,
        preserve_overlaps=False,
        render_error_cls=Err,
    )
    assert srt_path.is_file()
    assert "你好" in srt_path.read_text(encoding="utf-8")
    assert srt_stable is not None


def test_burn_or_copy_subs_off_copies(tmp_path: Path) -> None:
    silent = tmp_path / "silent.mp4"
    silent.write_bytes(b"fake-video")
    work = tmp_path / "work"
    work.mkdir()
    overlays = work / "overlays"
    overlays.mkdir()
    args = SimpleNamespace(subs="off")
    video_subbed, mode = burn_or_copy_subs(
        args=args,
        silent=silent,
        work=work,
        overlays_dir=overlays,
        cues=[{"start": 0.0, "end": 1.0, "text": "x", "shot_index": 0}],
        shot_dicts=[{}],
        width=720,
        height=1280,
        font_path="",
        run=lambda *a, **k: None,
    )
    assert mode == "off"
    assert video_subbed.is_file()
    assert video_subbed.read_bytes() == b"fake-video"


def test_materialize_exports() -> None:
    from final.stages_subs import (
        build_final_cues,
        burn_or_copy_subs,
        materialize_subs_stage,
        write_final_srt,
    )

    assert callable(materialize_subs_stage)
    assert callable(build_final_cues)
    assert callable(write_final_srt)
    assert callable(burn_or_copy_subs)
