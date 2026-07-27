from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dailies import update_dailies  # noqa: E402
from next_actions import build_next_actions  # noqa: E402
from quality_closure import (  # noqa: E402
    build_benchmark_package,
    build_quality_report,
    record_blind_review,
    repair_action,
)
from util import sha256_file  # noqa: E402

SCORES = {
    "narrative_rhythm": 4,
    "identity_continuity": 4,
    "performance": 4,
    "cinematography": 4,
    "motion_credibility": 4,
    "sound": 4,
    "caption_readability": 4,
    "overall_completion": 4,
}


def _premium_root(root: Path) -> None:
    (root / "production-book.json").write_text('{"quality_target":"premium_vertical"}')
    (root / "film-spec.json").write_text(
        '{"aspect":"9:16","shots":[{"id":"s001"}],"caption_owner":"hyperframes"}'
    )


def test_benchmark_package_is_versioned_and_no_spend(tmp_path: Path) -> None:
    _premium_root(tmp_path)

    report = build_benchmark_package(tmp_path)

    assert report["ok"] is True
    assert report["benchmark_version"] == "premium-vertical-v1"
    assert report["spend_authorized"] is False
    assert report["requirements"]["continue_endpoint_match"] is True
    assert (tmp_path / "receipts" / "premium-benchmark-package.json").is_file()


def test_blind_reviews_require_distinct_reviewers_and_report_disagreement(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)
    record_blind_review(tmp_path, reviewer="reviewer-a", scores=SCORES, notes="good")
    divergent = {**SCORES, "motion_credibility": 2}
    report = record_blind_review(tmp_path, reviewer="reviewer-b", scores=divergent, notes="motion")

    assert report["review_count"] == 2
    assert report["independent_review_complete"] is True
    assert report["disagreements"][0]["dimension"] == "motion_credibility"
    assert report["reshoot_queue"][0]["code"] == "MOTION_CREDIBILITY_LOW"


def test_quality_report_does_not_claim_artistic_verification_from_contracts(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)

    report = build_quality_report(tmp_path)

    assert report["evidence"]["contract"]["present"] is True
    assert report["evidence"]["real_provider"]["present"] is False
    assert report["claims"]["artistic_quality_verified"] is False
    assert "REAL_PROVIDER_MEDIA_MISSING" in report["blocking_codes"]


def test_quality_report_rejects_stale_or_forged_provider_receipt(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)
    (tmp_path / "receipts").mkdir(exist_ok=True)
    clip = tmp_path / "clips" / "forged.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"locally forged")
    (tmp_path / "receipts" / "provider-canary.json").write_text(
        '{"ok":true,"output":"clips/forged.mp4","output_sha256":"'
        + sha256_file(clip)
        + '","human_review_required":true}'
    )

    report = build_quality_report(tmp_path)

    assert report["evidence"]["real_provider"]["present"] is False
    assert "REAL_PROVIDER_MEDIA_MISSING" in report["blocking_codes"]


def test_quality_report_requires_matching_registered_provider_clip(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)
    clip = tmp_path / "clips" / "provider.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"provider output")
    digest = sha256_file(clip)
    (tmp_path / "manifest.json").write_text(
        '{"clips":{"s001":{"path":"'
        + str(clip)
        + '","sha256":"'
        + digest
        + '","status":"approved","active":true,"source_endpoint":"image_to_video"}}}'
    )
    (tmp_path / "receipts" / "provider-canary.json").write_text(
        '{"ok":true,"provider":"grok","output":"'
        + str(clip)
        + '","output_sha256":"'
        + digest
        + '","human_review_required":true}'
    )

    report = build_quality_report(tmp_path)

    assert report["evidence"]["real_provider"]["present"] is True


def test_quality_report_blocks_current_contract_without_per_shot_evidence(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)
    clip = tmp_path / "clips" / "provider.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"provider output")
    digest = sha256_file(clip)
    (tmp_path / "manifest.json").write_text(
        '{"quality_evidence_contract_version":1,"clips":{"s001":{"path":"'
        + str(clip)
        + '","sha256":"'
        + digest
        + '","status":"approved","active":true,"uniqueness":{"sha256":"'
        + digest
        + '"}}}}'
    )

    report = build_quality_report(tmp_path)

    assert report["evidence"]["shot_quality"]["ok"] is False
    assert "SHOT_QUALITY_EVIDENCE_MISSING" in report["blocking_codes"]


def test_repair_action_prefers_the_highest_priority_review_failure(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    build_benchmark_package(tmp_path)
    weak_identity = {**SCORES, "identity_continuity": 1, "caption_readability": 1}
    record_blind_review(tmp_path, reviewer="reviewer-a", scores=weak_identity, notes="bad")
    record_blind_review(tmp_path, reviewer="reviewer-b", scores=weak_identity, notes="bad")

    action = repair_action(tmp_path)

    assert action is not None
    assert action["code"] == "IDENTITY_CONTINUITY_LOW"
    assert action["evidence"]["kind"] == "blind-review"
    assert "register-still" in action["cmd"]


def test_reviewer_cannot_submit_twice(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    record_blind_review(tmp_path, reviewer="reviewer-a", scores=SCORES, notes="one")

    with pytest.raises(ValueError, match="already submitted"):
        record_blind_review(tmp_path, reviewer="reviewer-a", scores=SCORES, notes="two")


def test_reviewer_identity_is_casefolded_for_duplicate_protection(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    record_blind_review(tmp_path, reviewer="Reviewer", scores=SCORES, notes="one")

    with pytest.raises(ValueError, match="already submitted"):
        record_blind_review(tmp_path, reviewer="reviewer", scores=SCORES, notes="two")


def test_next_returns_only_the_evidence_backed_quality_repair(tmp_path: Path) -> None:
    _premium_root(tmp_path)
    weak_identity = {**SCORES, "identity_continuity": 1}
    record_blind_review(tmp_path, reviewer="reviewer-a", scores=weak_identity, notes="bad")
    record_blind_review(tmp_path, reviewer="reviewer-b", scores=weak_identity, notes="bad")

    actions = build_next_actions(
        tmp_path, gates={"brief": True, "style_locked": True, "spec": True}
    )

    assert len(actions) == 1
    assert actions[0]["code"] == "IDENTITY_CONTINUITY_LOW"


def test_dailies_binds_generation_and_director_selection_evidence(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")

    report = update_dailies(
        tmp_path,
        shot_id="s001",
        candidate=str(clip),
        status="reshoot",
        reviewer="director",
        notes="motion breaks",
        provider="grok",
        model="grok-imagine-video",
        cost_usd=0.12,
        source_keyframe="assets/s001.png",
        qa={"motion_score": 0.2},
        director_score=2,
        issue_tags=["motion", "identity", "motion"],
        reshoot_decision="reshoot",
        selection_rationale="not selected",
    )

    entry = report["shots"]["s001"][0]
    assert entry["generation"]["cost_usd"] == 0.12
    assert entry["objective_qa"]["motion_score"] == 0.2
    assert entry["issue_tags"] == ["identity", "motion"]
    assert entry["reshoot_decision"] == "reshoot"


def test_dailies_rejects_conflicting_reshoot_status_and_decision(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")

    with pytest.raises(ValueError, match="reshoot status"):
        update_dailies(
            tmp_path,
            shot_id="s001",
            candidate=str(clip),
            status="reshoot",
            reviewer="director",
            notes="bad",
            reshoot_decision="none",
        )
