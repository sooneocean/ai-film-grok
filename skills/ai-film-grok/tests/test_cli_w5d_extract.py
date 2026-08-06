"""W5d · orchestrate/oauth/evidence/bootstrap extract: public cmd strings still route."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_build_parser_has_w5d_cmds() -> None:
    from aifilm_grok import build_parser

    p = build_parser()
    cases = [
        ["next", "--root", "/tmp/film"],
        ["stage", "--root", "/tmp/film"],
        ["dispatch", "--root", "/tmp/film"],
        ["advance", "--root", "/tmp/film"],
        ["autopilot", "--root", "/tmp/film"],
        ["craft", "--root", "/tmp/film"],
        ["selects", "--root", "/tmp/film"],
        ["grok-oauth", "doctor"],
        ["usage", "status", "--root", "/tmp/film"],
        ["state-index", "check", "--root", "/tmp/film"],
        ["promotion-report", "--root", "/tmp/film"],
        ["production-evidence", "--root", "/tmp/film"],
        ["speech-preview", "probe"],
        ["lock-runtime"],
        ["resume-manifest", "--root", "/tmp/film"],
    ]
    for argv in cases:
        ns = p.parse_args(argv)
        assert ns.cmd == argv[0]


def test_cmd_handlers_imported_from_extract_modules() -> None:
    import aifilm_grok
    import cli_bootstrap
    import cli_evidence
    import cli_oauth
    import cli_orchestrate

    assert aifilm_grok.cmd_next is cli_orchestrate.cmd_next
    assert aifilm_grok.cmd_stage is cli_orchestrate.cmd_stage
    assert aifilm_grok.cmd_dispatch is cli_orchestrate.cmd_dispatch
    assert aifilm_grok.cmd_advance is cli_orchestrate.cmd_advance
    assert aifilm_grok.cmd_autopilot is cli_orchestrate.cmd_autopilot
    assert aifilm_grok.cmd_craft is cli_orchestrate.cmd_craft
    assert aifilm_grok.cmd_selects is cli_orchestrate.cmd_selects
    assert aifilm_grok.cmd_grok_oauth is cli_oauth.cmd_grok_oauth
    assert aifilm_grok.cmd_generation_usage is cli_oauth.cmd_generation_usage
    assert aifilm_grok.cmd_state_index is cli_evidence.cmd_state_index
    assert aifilm_grok.cmd_promotion_report is cli_evidence.cmd_promotion_report
    assert aifilm_grok.cmd_production_evidence is cli_evidence.cmd_production_evidence
    assert aifilm_grok.cmd_speech_preview is cli_evidence.cmd_speech_preview
    assert aifilm_grok.cmd_lock_runtime is cli_bootstrap.cmd_lock_runtime
    assert aifilm_grok.cmd_resume_manifest is cli_bootstrap.cmd_resume_manifest


def test_extracted_modules_importable() -> None:
    import cli_bootstrap
    import cli_evidence
    import cli_oauth
    import cli_orchestrate

    assert callable(cli_orchestrate.cmd_dispatch)
    assert callable(cli_oauth.cmd_grok_oauth)
    assert callable(cli_evidence.cmd_state_index)
    assert callable(cli_bootstrap.cmd_lock_runtime)


def test_add_w5d_parsers_callable() -> None:
    import argparse

    from cli_bootstrap import add_bootstrap_parsers
    from cli_evidence import add_evidence_parsers
    from cli_oauth import add_oauth_parsers
    from cli_orchestrate import add_orchestrate_parsers

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_bootstrap_parsers(sub)
    add_oauth_parsers(sub)
    add_orchestrate_parsers(sub)
    add_evidence_parsers(sub)
    assert p.parse_args(["dispatch", "--root", "/x"]).cmd == "dispatch"
    assert p.parse_args(["grok-oauth", "doctor"]).cmd == "grok-oauth"
    assert p.parse_args(["state-index", "check", "--root", "/x"]).cmd == "state-index"
    assert p.parse_args(["lock-runtime"]).cmd == "lock-runtime"
