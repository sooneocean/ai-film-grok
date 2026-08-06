from __future__ import annotations

import sys
import wave
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from optimization_dashboard import build as build_dashboard  # noqa: E402
from optimization_program import (  # noqa: E402
    approve_formal_stage,
    evaluate_challenger,
    init_program,
    record_audio_lane,
    record_draft_stage,
    weekly_summary,
)


def _metrics(*, root: str, passed: bool = True, challenger: str | None = None) -> dict:
    report = {
        "kind": "optimization-metrics",
        "metadata": {"film_root": root, **({"challenger": challenger} if challenger else {})},
        "data_quality": {"state": "known"},
        "l0": {"all_pass": passed},
        "l1": {"motion_score": {"p10": 4.2}, "motion_fail_rate": 0.1},
        "l2": {"approved": passed, "grade_summary": {"p50": 4.0}},
        "l3": {
            "stage_yield": 0.8,
            "usd_per_pass_min": 1.2,
            "sec_per_shot_i2v": {"p50": 18.0},
            "retry_count": 1,
            "human_minutes": 2.5,
        },
    }
    from util import canonical_json_sha256

    report["content_sha256"] = canonical_json_sha256(report)
    return report


def test_program_has_named_challengers_audio_lanes_and_single_post_owner(tmp_path: Path) -> None:
    program = init_program(tmp_path)

    assert set(program["challengers"]) == {
        "infinitetalk",
        "ltx-fast",
        "hunyuan-720p-sr",
        "realesrgan-animevideo",
    }
    assert set(program["audio_lanes"]) == {"qwen3-tts", "ace-step", "stable-audio", "mmaudio"}
    assert program["post_policy"]["allowed_owners"] == ["hyperframes", "remotion"]
    assert len(program["weekly_metrics"]) == 10


def test_formal_stage_requires_a_passing_draft_and_never_changes_default_route(
    tmp_path: Path,
) -> None:
    init_program(tmp_path)
    evidence = tmp_path / "hunyuan-review.json"
    evidence.write_text(
        '{"reviewer":"dex","720p_decode":true,"sr_artifact_review":true,"human_visual_review":true}'
    )
    with pytest.raises(ValueError, match="draft receipt"):
        approve_formal_stage(
            tmp_path,
            shot_id="s1",
            formal_model="hunyuan-720p-sr",
            evidence_receipt=evidence,
        )

    draft = record_draft_stage(
        tmp_path,
        shot_id="s1",
        model="ltx-fast",
        still_approved=True,
        composition_pass=True,
        motion_pass=True,
        continuity_pass=True,
    )
    formal = approve_formal_stage(
        tmp_path,
        shot_id="s1",
        formal_model="hunyuan-720p-sr",
        evidence_receipt=evidence,
    )

    assert draft["stage"] == "draft"
    assert formal["stage"] == "formal_authorized"
    assert formal["automatic_provider_dispatch"] is False
    assert formal["changes_default_route"] is False


def test_challenger_needs_three_complete_known_non_regressing_projects(tmp_path: Path) -> None:
    init_program(tmp_path)
    with pytest.raises(ValueError, match="three"):
        evaluate_challenger(
            tmp_path,
            challenger="ltx-fast",
            reports=[_metrics(root="one", challenger="ltx-fast")],
            baseline_reports=[_metrics(root="base-one")],
        )

    report = evaluate_challenger(
        tmp_path,
        challenger="ltx-fast",
        reports=[
            _metrics(root="one", challenger="ltx-fast"),
            _metrics(root="two", challenger="ltx-fast"),
            _metrics(root="three", challenger="ltx-fast"),
        ],
        baseline_reports=[
            _metrics(root="base-one"),
            _metrics(root="base-two"),
            _metrics(root="base-three"),
        ],
    )

    assert report["recommendation"] == "request_human_promotion"
    assert report["automatic_promotion"] is False


def test_audio_lane_requires_readback_and_human_review(tmp_path: Path) -> None:
    init_program(tmp_path)
    artifact = tmp_path / "candidate.wav"
    with wave.open(str(artifact), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\0\0" * 8000)
    review = tmp_path / "review.json"
    from util import sha256_file

    review.write_text(
        '{"human_reviewed":true,"reviewer":"dex","artifact_sha256":"' + sha256_file(artifact) + '"}'
    )
    with pytest.raises(ValueError, match="review_receipt"):
        record_audio_lane(
            tmp_path,
            lane="mmaudio",
            artifact=artifact,
            review_receipt=tmp_path / "missing.json",
            production_eligible=False,
        )
    receipt = record_audio_lane(
        tmp_path,
        lane="mmaudio",
        artifact=artifact,
        review_receipt=review,
        production_eligible=False,
    )
    assert receipt["status"] == "reviewed_candidate"


def test_weekly_summary_has_exactly_ten_known_or_unknown_metrics(tmp_path: Path) -> None:
    summary = weekly_summary([_metrics(root="one"), {"data_quality": {"state": "unknown"}}])

    assert summary["data_quality"] == "partial"
    assert len(summary["metrics"]) == 10
    assert summary["metrics"]["usd_per_pass_min"]["value"] == 1.2


def test_program_cli_preserves_no_spend_command_contract() -> None:
    import argparse

    from cli_optimization import add_optimization_parsers

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    add_optimization_parsers(subparsers)
    args = parser.parse_args(
        [
            "optimization-program",
            "draft",
            "--root",
            "film",
            "--shot-id",
            "s1",
            "--model",
            "ltx-fast",
            "--still-approved",
            "--composition-pass",
            "--motion-pass",
            "--continuity-pass",
        ]
    )
    assert args.program_action == "draft"
    assert args.motion_pass is True

    evaluate = parser.parse_args(
        [
            "optimization-program",
            "evaluate",
            "--root",
            "film",
            "--challenger",
            "ltx-fast",
            "--metrics-root",
            "run-one",
            "--metrics-root",
            "run-two",
            "--metrics-root",
            "run-three",
            "--baseline-metrics-root",
            "base-one",
            "--baseline-metrics-root",
            "base-two",
            "--baseline-metrics-root",
            "base-three",
        ]
    )
    assert evaluate.program_action == "evaluate"
    assert len(evaluate.metrics_root) == 3


def test_dashboard_exposes_all_ten_weekly_metrics(tmp_path: Path) -> None:
    film = tmp_path / "film"
    (film / "receipts").mkdir(parents=True)
    from util import write_json

    write_json(
        film / "receipts" / "metrics.json",
        {"kind": "optimization-metrics", **_metrics(root="film")},
    )
    report = build_dashboard(tmp_path, days=3650, out=tmp_path / "dashboard")
    assert len(report["weekly_summary"]["metrics"]) == 10
