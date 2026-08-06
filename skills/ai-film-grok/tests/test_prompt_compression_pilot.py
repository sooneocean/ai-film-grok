from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prompt_compression_pilot import (  # noqa: E402
    attest_prompt_compression_pilot,
    build_prompt_compression_pilot,
)


def _source_receipt(root: Path) -> None:
    receipts = root / "receipts"
    receipts.mkdir()
    (receipts / "prompt_assembly_s1.json").write_text(
        json.dumps(
            {
                "shot_id": "s1",
                "prompt_hash": "source-hash",
                "prompt_text": "Style: ink wash\nCostume continuity HARD: same wardrobe\nNo labels or watermark",
            }
        ),
        encoding="utf-8",
    )


def test_compression_pilot_binds_hashes_without_mutating_source(tmp_path: Path) -> None:
    _source_receipt(tmp_path)
    original = (tmp_path / "receipts" / "prompt_assembly_s1.json").read_text(encoding="utf-8")
    report = build_prompt_compression_pilot(
        tmp_path,
        {
            "candidate_id": "no-labels",
            "source_line": "No labels or watermark",
            "shots": [
                {
                    "shot_id": "s1",
                    "candidate_prompt_text": "Style: ink wash\nCostume continuity HARD: same wardrobe",
                }
            ],
        },
    )

    assert report["state"] == "needs_pilot_evidence"
    assert report["approval"] == "not_granted"
    assert report["bindings"][0]["source_prompt_hash"] == "source-hash"
    assert (tmp_path / "receipts" / "prompt-compression-pilot.json").is_file()
    assert (tmp_path / "receipts" / "prompt_assembly_s1.json").read_text(
        encoding="utf-8"
    ) == original


def test_compression_pilot_rejects_removal_of_protected_lock(tmp_path: Path) -> None:
    _source_receipt(tmp_path)

    with pytest.raises(ValueError, match="protected"):
        build_prompt_compression_pilot(
            tmp_path,
            {
                "source_line": "No labels or watermark",
                "shots": [{"shot_id": "s1", "candidate_prompt_text": "Action: enters"}],
            },
        )


def test_attestation_binds_real_artifacts_but_does_not_promote(tmp_path: Path) -> None:
    _source_receipt(tmp_path)
    build_prompt_compression_pilot(
        tmp_path,
        {
            "candidate_id": "no-labels",
            "source_line": "No labels or watermark",
            "shots": [
                {
                    "shot_id": "s1",
                    "candidate_prompt_text": "Style: ink wash\nCostume continuity HARD: same wardrobe",
                }
            ],
        },
    )
    for relative in ("stills/s1.png", "clips/s1.mp4", "receipts/s1-frame-qa.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence", encoding="utf-8")
    (tmp_path / "receipts" / "pilot-scorecard.json").write_text(
        json.dumps(
            {
                "kind": "pilot-scorecard",
                "shots": ["s1"],
                "dimensions": {"identity": True, "style": True, "motion": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "receipts" / "pilot-approval.json").write_text(
        json.dumps({"approved": True, "shots": ["s1"]}), encoding="utf-8"
    )
    ledger = json.loads(
        (tmp_path / "receipts" / "prompt-compression-pilot.json").read_text(encoding="utf-8")
    )

    report = attest_prompt_compression_pilot(
        tmp_path,
        {
            "candidate_id": "no-labels",
            "shots": [
                {
                    "shot_id": "s1",
                    "candidate_prompt_hash": ledger["bindings"][0]["candidate_prompt_hash"],
                    "keyframe_path": "stills/s1.png",
                    "clip_path": "clips/s1.mp4",
                    "frame_qa_path": "receipts/s1-frame-qa.json",
                }
            ],
        },
        user_phrase="pilot 过",
    )

    assert report["state"] == "evidence_complete_not_promoted"
    assert (tmp_path / "receipts" / "prompt-compression-pilot-attestation.json").is_file()
    updated = json.loads(
        (tmp_path / "receipts" / "prompt-compression-pilot.json").read_text(encoding="utf-8")
    )
    assert updated["approval"] == "human_pilot_approved_not_promoted"
