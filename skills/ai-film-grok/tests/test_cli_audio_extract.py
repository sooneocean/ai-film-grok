"""W5c · cli_audio extract: public audio/tts/lipsync strings still route."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_build_parser_has_audio_cmds() -> None:
    from aifilm_grok import build_parser

    p = build_parser()
    cases = [
        ["audio-plan", "--root", "/tmp/film"],
        ["audio-verify", "--root", "/tmp/film"],
        ["verify", "--root", "/tmp/film"],
        ["tts-rehearse", "--root", "/tmp/film"],
        ["lipsync-node"],
        ["capability"],
        ["bgm-candidate", "list", "--root", "/tmp/film"],
        ["sfx-library", "audit"],
    ]
    for argv in cases:
        ns = p.parse_args(argv)
        assert ns.cmd == argv[0]


def test_cmd_audio_imported_from_cli_audio() -> None:
    import aifilm_grok
    import cli_audio

    assert aifilm_grok.cmd_audio_plan is cli_audio.cmd_audio_plan
    assert aifilm_grok.cmd_tts_rehearse is cli_audio.cmd_tts_rehearse
    assert aifilm_grok.cmd_lipsync_node is cli_audio.cmd_lipsync_node
    assert aifilm_grok.cmd_verify is cli_audio.cmd_verify


def test_add_audio_parsers_callable() -> None:
    import argparse

    from cli_audio import add_audio_parsers

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_audio_parsers(sub)
    ns = p.parse_args(["audio-plan", "--root", "/x"])
    assert ns.cmd == "audio-plan"
