from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import build_parser  # noqa: E402
from director_review import SCORECARD_DIMENSIONS  # noqa: E402
from final_review_input import (  # noqa: E402
    FinalReviewInputError,
    apply_review_input,
    write_review_input,
)


def _payload(final_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "kind": "final-review-input",
        "approve": True,
        "reviewer": "dex",
        "notes": "完整观看并核对画面、声音、字幕和结尾。",
        "watched_full": True,
        "final_output_sha256": final_sha256,
        "human_minutes": 3.5,
        "scorecard": {dimension: "pass" for dimension in SCORECARD_DIMENSIONS},
        "grades": {dimension: 4 for dimension in SCORECARD_DIMENSIONS},
        "screening_evidence": {
            dimension: {"timestamp_sec": index + 0.5, "note": f"checked {dimension}"}
            for index, dimension in enumerate(SCORECARD_DIMENSIONS)
        },
        "fail_reasons": {},
        "reshoot_shots": [],
    }


def _root(path: Path, final_sha256: str) -> None:
    (path / "receipts").mkdir()
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "review_contract_version": 3,
                "outputs": {"final_film": {"sha256": final_sha256}},
            }
        ),
        encoding="utf-8",
    )


def test_review_file_replaces_thirty_plus_cli_flags(tmp_path: Path) -> None:
    final_sha256 = "a" * 64
    _root(tmp_path, final_sha256)
    receipt = write_review_input(tmp_path, _payload(final_sha256))
    args = argparse.Namespace(
        approve=False,
        reviewer=None,
        notes=None,
        watched_full=False,
        screening_evidence=[],
        fail_reason=[],
        reshoot_shots="",
    )
    for dimension in SCORECARD_DIMENSIONS:
        setattr(args, f"score_{dimension}", None)
        setattr(args, f"grade_{dimension}", None)

    loaded = apply_review_input(args, root=tmp_path, path=receipt["path"])

    assert loaded["final_output_sha256"] == final_sha256
    assert args.approve is True
    assert args.reviewer == "dex"
    assert args.watched_full is True
    assert args.score_identity == "pass"
    assert args.grade_performance == 4
    assert len(args.screening_evidence) == len(SCORECARD_DIMENSIONS)


def test_review_file_rejects_stale_final_hash(tmp_path: Path) -> None:
    _root(tmp_path, "a" * 64)

    with pytest.raises(FinalReviewInputError, match="current final"):
        write_review_input(tmp_path, _payload("b" * 64))


def test_review_final_parser_accepts_review_file_without_duplicate_flags() -> None:
    args = build_parser().parse_args(
        ["review-final", "--root", "/tmp/film", "--review-file", "receipts/review.json"]
    )

    assert args.review_file == "receipts/review.json"
    assert args.reviewer is None
    assert args.notes is None
