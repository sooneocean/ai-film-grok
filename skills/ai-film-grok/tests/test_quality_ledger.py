from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from pipeline_events import append_event  # noqa: E402
from quality_ledger import (  # noqa: E402
    QualityLedgerError,
    emit_quality_ledger,
    record_retrospective,
)


def _root(path: Path, *, unknown_cost: bool = False) -> None:
    (path / "receipts").mkdir(parents=True)
    (path / "out").mkdir()
    (path / "film-spec.json").write_text('{"shots":[{"id":"s1"}]}')
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "gates": {"final_complete": True},
                "clips": {
                    "s1": {
                        "status": "approved",
                        "identity_approved": True,
                        "motion_approved": True,
                        "uniqueness": {"sha256": "a" * 64},
                        "qa": {"ok": True, "motion_score": 4.5},
                    }
                },
                "outputs": {"final_film": {"sha256": "b" * 64, "duration_sec": 60}},
            }
        )
    )
    (path / "out" / "final-review.json").write_text(
        json.dumps(
            {
                "approved": True,
                "grades": {"motion": 4},
                "scorecard": {"dimensions": {"motion": True}},
            }
        )
    )
    finished = {
        "generation_id": "g1",
        "phase": "finished",
        "status": "succeeded",
        "measurement": "unknown" if unknown_cost else "provider_exact",
        "usage": {} if unknown_cost else {"cost_in_usd_ticks": 123},
        "recorded_at": "2026-01-01T00:00:01Z",
    }
    (path / "receipts" / "generation-usage.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "generation-usage",
                "events": [
                    {
                        "generation_id": "g1",
                        "phase": "started",
                        "operation": "i2v",
                        "provider": "provider",
                        "shot_id": "s1",
                        "recorded_at": "2026-01-01T00:00:00Z",
                    },
                    finished,
                ],
            }
        )
    )
    append_event(path, stage="init", phase="completed", occurred_at="2026-01-01T00:00:00Z")
    append_event(path, stage="review-final", phase="completed", occurred_at="2026-01-01T00:01:00Z")


def test_emit_keeps_unknown_cost_unknown_and_retains_manual_data(tmp_path: Path) -> None:
    _root(tmp_path, unknown_cost=True)
    first = emit_quality_ledger(tmp_path)
    assert first["shots"][0]["generation"]["cost_in_usd_ticks"] is None
    assert first["shots"][0]["generation"]["unknown_cost_attempts"] == 1
    assert first["generation"]["cost_in_usd_ticks"] is None
    assert first["generation"]["cost_usd"] is None
    assert first["generation"]["cost_state"] == "unknown"
    recorded = record_retrospective(
        tmp_path,
        director_score=82,
        worth_publishing=True,
        p0_improvement="Repair motion state evidence before the next pilot.",
        reshoot_reasons=["s1: ending pose is unclear"],
    )
    refreshed = emit_quality_ledger(tmp_path)
    assert recorded["retrospective_complete"] is True
    assert refreshed["manual"]["director_score"] == 82
    assert refreshed["manual"]["worth_publishing"] is True
    assert refreshed["manual"]["reshoot_reasons"] == ["s1: ending pose is unclear"]


def test_record_requires_one_bounded_p0_improvement(tmp_path: Path) -> None:
    _root(tmp_path)
    with pytest.raises(QualityLedgerError, match="p0_improvement"):
        record_retrospective(
            tmp_path,
            director_score=80,
            worth_publishing=False,
            p0_improvement="",
            reshoot_reasons=[],
        )


def test_quality_reporting_parser_domain_preserves_command_contract() -> None:
    from cli_quality_reporting import add_quality_reporting_parsers

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    add_quality_reporting_parsers(subparsers)

    record = parser.parse_args(
        [
            "quality-ledger",
            "record",
            "--root",
            "film",
            "--director-score",
            "82",
            "--worth-publishing",
            "--p0-improvement",
            "Repair the action state.",
            "--reshoot-reason",
            "s1: pose unclear",
        ]
    )
    report = parser.parse_args(
        ["production-report", "emit", "--root", "film", "--history-root", "library"]
    )

    assert record.quality_ledger_action == "record"
    assert record.reshoot_reason == ["s1: pose unclear"]
    assert report.production_report_action == "emit"
    assert report.history_root == "library"


def test_cli_record_rejects_a_film_without_an_approved_final(tmp_path: Path) -> None:
    _root(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["gates"]["final_complete"] = False
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "out" / "final-review.json").write_text(json.dumps({"approved": False}))
    assert (
        aifilm_grok.main(
            [
                "quality-ledger",
                "record",
                "--root",
                str(tmp_path),
                "--director-score",
                "80",
                "--p0-improvement",
                "Fix the start and end state before the next pilot.",
            ]
        )
        == 2
    )
