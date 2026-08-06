"""W5b · cli_write_spec extract: public write-spec still routes + shipped templates."""

from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from io import StringIO
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[1]
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


def test_shipped_film_spec_templates_write_spec_ok() -> None:
    """Shipped templates must clear the real write-spec entry (cinematic + empty bible)."""
    import aifilm_grok

    templates = sorted((ROOT / "templates").glob("film-spec*.json"))
    assert len(templates) >= 4
    for path in templates:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "film"
            with contextlib.redirect_stdout(StringIO()):
                assert (
                    aifilm_grok.main(
                        ["init", "--theme", "test", "--title", "test", "--root", str(root)]
                    )
                    == 0
                )
            source = base / "incoming.json"
            source.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            out = StringIO()
            with contextlib.redirect_stdout(out):
                rc = aifilm_grok.main(
                    ["write-spec", "--root", str(root), "--spec", str(source)]
                )
            payload = json.loads(out.getvalue())
            assert rc == 0, (path.name, payload)
            assert payload.get("ok") is True, (path.name, payload)
            assert int(payload.get("shot_count") or 0) >= 1