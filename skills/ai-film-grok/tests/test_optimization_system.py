from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gold_calibration import calibrate
from optimization_dashboard import build as build_dashboard
from optimization_experiments import (
    decide,
    diff_experiment,
    import_arm,
    init_experiment,
    run_request,
)
from optimization_metrics import emit_metrics
from pipeline_events import append_event


def _root(
    path: Path,
    *,
    cost_ticks: int | None = 1000000000,
    include_human_time: bool = True,
) -> None:
    (path / "receipts").mkdir(parents=True)
    (path / "film-spec.json").write_text('{"shots":[{"id":"s1"}]}')
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "gates": {"final_complete": True},
                "clips": {"s1": {"status": "approved", "qa": {"ok": True, "motion_score": 5.0}}},
                "outputs": {"final_film": {"sha256": "a" * 64, "duration_sec": 60}},
            }
        )
    )
    review = {
        "approved": True,
        "scorecard": {
            "dimensions": {
                key: True
                for key in (
                    "identity",
                    "style",
                    "motion",
                    "escalation",
                    "audio",
                    "subs",
                    "dead_air",
                    "rhythm",
                    "emotion",
                    "theme",
                    "performance",
                )
            }
        },
        "grades": {
            key: 4
            for key in (
                "identity",
                "style",
                "motion",
                "escalation",
                "audio",
                "subs",
                "dead_air",
                "rhythm",
                "emotion",
                "theme",
                "performance",
            )
        },
    }
    (path / "out").mkdir()
    (path / "out" / "final-review.json").write_text(json.dumps(review))
    usage = {"schema_version": 1, "kind": "generation-usage", "events": []}
    if cost_ticks is not None:
        usage["events"] = [
            {
                "generation_id": "g",
                "phase": "started",
                "operation": "i2v",
                "provider": "p",
                "recorded_at": "2026-01-01T00:00:00Z",
            },
            {
                "generation_id": "g",
                "phase": "finished",
                "status": "succeeded",
                "measurement": "provider_exact",
                "usage": {"cost_in_usd_ticks": cost_ticks},
                "recorded_at": "2026-01-01T00:00:01Z",
            },
        ]
    (path / "receipts" / "generation-usage.json").write_text(json.dumps(usage))
    append_event(path, stage="init", phase="completed", occurred_at="2026-01-01T00:00:00Z")
    append_event(
        path, stage="i2v", phase="claimed", shot_id="s1", occurred_at="2026-01-01T00:00:02Z"
    )
    append_event(
        path, stage="i2v", phase="registered", shot_id="s1", occurred_at="2026-01-01T00:00:12Z"
    )
    append_event(path, stage="review-final", phase="completed", occurred_at="2026-01-01T00:01:00Z")
    if include_human_time:
        append_event(
            path,
            stage="review-final",
            phase="human_time",
            occurred_at="2026-01-01T00:01:00Z",
            human_minutes=1.0,
        )


def test_metrics_preserve_unknown_cost_and_event_time(tmp_path: Path) -> None:
    _root(tmp_path, cost_ticks=None)
    report = emit_metrics(tmp_path)
    assert report["l3"]["cost_usd"] is None
    assert report["l3"]["wall_sec_init_to_verified"] == 60
    assert report["l3"]["sec_per_shot_i2v"]["p50"] == 10


def test_metrics_never_turn_missing_production_evidence_into_zero(tmp_path: Path) -> None:
    _root(tmp_path, cost_ticks=None, include_human_time=False)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["gates"]["assembled"] = False
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    append_event(
        tmp_path,
        stage="i2v",
        phase="registered",
        shot_id="s1",
        occurred_at="2026-01-01T00:00:20Z",
    )
    append_event(
        tmp_path,
        stage="i2v",
        phase="registered",
        shot_id="s1",
        occurred_at="2026-01-01T00:00:30Z",
    )

    report = emit_metrics(tmp_path)

    assert report["l0"]["all_pass"] is False
    assert report["l3"]["human_minutes"] is None
    assert report["l3"]["human_time_state"] == "unknown"
    assert report["l3"]["cost_usd"] is None
    assert report["l3"]["i2v_cost_state"] == "unknown"
    assert report["l3"]["registered_event_count"] == 3
    assert report["l3"]["unique_registered_shots"] == 1
    assert report["l3"]["registration_rework_count"] == 2
    assert report["l3"]["stage_yield"] == pytest.approx(1 / 3, abs=0.0001)
    assert report["data_quality"]["state"] == "partial"
    assert "human_time" in report["data_quality"]["missing_evidence"]
    assert "i2v_cost" in report["data_quality"]["missing_evidence"]


def test_metrics_reads_current_plugin_version(tmp_path: Path) -> None:
    _root(tmp_path)
    expected = json.loads((SCRIPTS.parents[2] / "plugin.json").read_text(encoding="utf-8"))[
        "version"
    ]

    report = emit_metrics(tmp_path)

    assert report["metadata"]["plugin_version"] == expected


def test_experiment_requires_identical_contract_and_never_auto_spends(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "baseline", tmp_path / "treatment"
    _root(baseline)
    _root(treatment, cost_ticks=800000000)
    init_experiment(
        tmp_path,
        experiment_id="e1",
        hypothesis="cost down",
        treatment_axis="model",
        primary_metric="cost_usd",
        min_effect=0.2,
        fixtures=["C-motion"],
        seed="1",
        shot_count=2,
        aspect="9:16",
        duration_budget_sec=20,
    )
    config = {
        "fixtures": ["C-motion"],
        "seed": "1",
        "shot_count": 2,
        "aspect": "9:16",
        "duration_budget_sec": 20,
    }
    import_arm(tmp_path, experiment_id="e1", arm="baseline", metrics_root=baseline, config=config)
    import_arm(tmp_path, experiment_id="e1", arm="treatment", metrics_root=treatment, config=config)
    assert diff_experiment(tmp_path, experiment_id="e1")["relative_change"] == pytest.approx(-0.2)
    assert (
        run_request(
            tmp_path, experiment_id="e1", arm="baseline", authorize_spend=False, max_usd=None
        )["spend_authorized"]
        is False
    )
    assert decide(tmp_path, experiment_id="e1", decision="ship")["automatic_apply"] is False


def test_experiment_never_ships_partial_metrics(tmp_path: Path) -> None:
    baseline, treatment = tmp_path / "baseline", tmp_path / "treatment"
    _root(baseline)
    _root(treatment, cost_ticks=800000000)
    for root in (baseline, treatment):
        events = root / "receipts" / "pipeline-events.jsonl"
        rows = [
            line
            for line in events.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("phase") != "human_time"
        ]
        events.write_text("\n".join(rows) + "\n", encoding="utf-8")
        assert emit_metrics(root)["data_quality"]["state"] == "partial"
    init_experiment(
        tmp_path,
        experiment_id="partial",
        hypothesis="cost down",
        treatment_axis="model",
        primary_metric="cost_usd",
        min_effect=0.1,
        fixtures=["C-motion"],
        seed="1",
        shot_count=2,
        aspect="9:16",
        duration_budget_sec=20,
    )
    config = {
        "fixtures": ["C-motion"],
        "seed": "1",
        "shot_count": 2,
        "aspect": "9:16",
        "duration_budget_sec": 20,
    }
    import_arm(
        tmp_path,
        experiment_id="partial",
        arm="baseline",
        metrics_root=baseline,
        config=config,
    )
    import_arm(
        tmp_path,
        experiment_id="partial",
        arm="treatment",
        metrics_root=treatment,
        config=config,
    )

    report = diff_experiment(tmp_path, experiment_id="partial")

    assert report["unknown"] is True
    with pytest.raises(ValueError, match="adoption evidence"):
        decide(tmp_path, experiment_id="partial", decision="ship")


def test_gold_needs_twenty_hash_bound_double_reviews(tmp_path: Path) -> None:
    manifest = tmp_path / "gold.json"
    manifest.write_text(json.dumps({"items": []}))
    assert calibrate(manifest)["code"] == "GOLD_SAMPLE_TOO_SMALL"
    items = [
        {
            "id": str(index),
            "media_sha256": "a" * 64,
            "early_reject": index % 2 == 0,
            "reviews": [{"human_fail": index % 2 == 0}, {"human_fail": index % 2 == 0}],
        }
        for index in range(20)
    ]
    manifest.write_text(json.dumps({"items": items}))
    assert calibrate(manifest)["threshold_promotion_allowed"] is True


def test_dashboard_only_reads_metrics_receipts(tmp_path: Path) -> None:
    film = tmp_path / "films" / "one"
    _root(film)
    emit_metrics(film)
    report = build_dashboard(tmp_path / "films", days=30, out=tmp_path / "dashboard")
    page = Path(report["out"]).read_text()
    assert report["counts"]["runs"] == 1
    assert "Optimisation dashboard" in page


def test_optimization_parser_domain_preserves_command_contract() -> None:
    from cli_optimization import add_optimization_parsers

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    add_optimization_parsers(subparsers)

    metrics = parser.parse_args(["metrics", "emit", "--root", "film", "--run-id", "run-1"])
    experiment = parser.parse_args(
        [
            "experiment",
            "run",
            "--root",
            "film",
            "--id",
            "exp-1",
            "--arm",
            "treatment",
            "--authorize-spend",
            "--max-usd",
            "3.5",
        ]
    )
    gold = parser.parse_args(["gold", "calibrate", "--manifest", "gold.json"])
    dashboard = parser.parse_args(
        ["dashboard", "build", "--roots-dir", "films", "--days", "14", "--out", "dashboard"]
    )

    assert metrics.metrics_action == "emit"
    assert metrics.run_id == "run-1"
    assert experiment.experiment_action == "run"
    assert experiment.authorize_spend is True
    assert experiment.max_usd == 3.5
    assert gold.gold_action == "calibrate"
    assert dashboard.dashboard_action == "build"
