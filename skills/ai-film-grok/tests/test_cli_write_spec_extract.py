"""W5b · cli_write_spec extract: public write-spec still routes."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_build_parser_has_write_spec() -> None:
    from aifilm_grok import build_parser

    ns = build_parser().parse_args(["write-spec", "--root", "/tmp/film"])
    assert ns.cmd == "write-spec"
    assert str(ns.root) in {"/tmp/film", "/tmp/film"}


def test_cmd_write_spec_imported_from_cli_write_spec() -> None:
    import aifilm_grok
    import cli_write_spec

    assert aifilm_grok.cmd_write_spec is cli_write_spec.cmd_write_spec


def test_compatibility_helpers_on_cli_write_spec() -> None:
    from cli_write_spec import (
        _compatibility_dramatic_functions,
        _compatibility_vo_mode,
    )

    out = _compatibility_vo_mode({"scenes": [{"shots": [{"id": "s1"}]}]})
    assert out.get("vo_mode") == "dialogue_drama"
    out2 = _compatibility_dramatic_functions(
        {"scenes": [{"shots": [{"id": "s1", "screen_mode": "reaction"}]}]}
    )
    shots = out2["scenes"][0]["shots"]
    assert shots[0].get("dramatic_function") == "reaction"
