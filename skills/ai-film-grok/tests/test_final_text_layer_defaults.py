"""Regression coverage for single-owner final text layers."""

from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
import render_final  # noqa: E402


def test_aifilm_final_defaults_to_hyperframes_with_no_plate_text() -> None:
    args = aifilm_grok.build_parser().parse_args(["final", "--root", "/tmp/film"])

    assert args.post_engine == "hyperframes"
    assert args.subs == "off"
    assert args.plate_cards == "blank"


def test_aifilm_explicit_ffmpeg_burn_remains_available() -> None:
    args = aifilm_grok.build_parser().parse_args(
        [
            "final",
            "--root",
            "/tmp/film",
            "--post-engine",
            "ffmpeg",
            "--subs",
            "burn",
            "--plate-cards",
            "text",
        ]
    )

    assert args.post_engine == "ffmpeg"
    assert args.subs == "burn"
    assert args.plate_cards == "text"


def test_render_final_direct_default_keeps_the_plate_text_free(monkeypatch) -> None:
    captured = {}

    def fake_render(args):
        captured["args"] = args
        return {"ok": True}

    monkeypatch.setattr(render_final, "render_final", fake_render)

    assert render_final.main(["--root", "/tmp/film"]) == 0
    assert captured["args"].subs == "off"
    assert captured["args"].plate_cards == "blank"


def test_render_final_subs_off_never_selects_the_burn_path() -> None:
    assert render_final.resolve_subtitle_mode(Namespace(subs="off")) == "off"
