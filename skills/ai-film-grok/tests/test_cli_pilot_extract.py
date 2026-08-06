"""W5 · cli_pilot extract: public pilot strings still route."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_build_parser_has_pilot_actions() -> None:
    from aifilm_grok import build_parser

    p = build_parser()
    for argv in (
        ["pilot", "pick", "--root", "/tmp/film"],
        ["pilot", "pack", "--root", "/tmp/film"],
        ["pilot", "report", "--root", "/tmp/film"],
        [
            "pilot",
            "score",
            "--root",
            "/tmp/film",
            "--shots",
            "s01",
            "--reviewer",
            "u",
            "--notes",
            "n",
            "--score-identity",
            "pass",
            "--score-style",
            "pass",
            "--score-motion",
            "pass",
        ],
        [
            "pilot",
            "approve",
            "--root",
            "/tmp/film",
            "--user-phrase",
            "pilot 过",
        ],
    ):
        ns = p.parse_args(argv)
        assert ns.cmd == "pilot"
        assert ns.pilot_action == argv[1]


def test_cmd_pilot_imported_from_cli_pilot() -> None:
    import aifilm_grok
    import cli_pilot

    assert aifilm_grok.cmd_pilot is cli_pilot.cmd_pilot


def test_simple_dispatch_maps_pilot() -> None:
    from aifilm_grok import build_parser, main

    # --help exits 0 without film root
    try:
        main(["pilot", "pack", "--help"])
    except SystemExit as exc:
        assert exc.code in (0, None)
