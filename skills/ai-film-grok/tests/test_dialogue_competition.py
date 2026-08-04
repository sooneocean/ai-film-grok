from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_competition import (  # noqa: E402
    approve_dialogue_candidate,
    build_dialogue_competition_plan,
    rank_dialogue_candidates,
    validate_dialogue_competition,
)

NOW = "2026-07-29T12:00:00+00:00"
STATE_HASH = "a" * 64
AUDIO_HASH = "b" * 64


def _shot() -> dict[str, object]:
    return {
        "id": "shot-dialogue-01",
        "shot_type": "speaking",
        "speaker": "heroine",
        "dialogue": "我就在这里。",
        "caption_text": "我就在这里。",
        "performance_intent": "quiet resolve, direct eyeline",
        "performance_state": {
            "status": "approved",
            "image_sha256": STATE_HASH,
        },
        "tts": {
            "status": "final",
            "language": "zh",
            "audio_sha256": AUDIO_HASH,
        },
    }


def _capability(
    capability_id: str,
    *,
    lane: str,
    promotion: str = "production",
    expires_at: str = "2026-07-30T12:00:00+00:00",
    canary_passed: bool = True,
) -> dict[str, object]:
    return {
        "id": capability_id,
        "lane": lane,
        "status": "ready",
        "verified_at": "2026-07-29T10:00:00+00:00",
        "expires_at": expires_at,
        "canary_passed": canary_passed,
        "promotion": promotion,
        "model": capability_id,
    }


def _capabilities(*, infinite_promotion: str = "pilot") -> list[dict[str, object]]:
    return [
        _capability("qwen-image-i2i", lane="state_i2i"),
        _capability("edge", lane="tts"),
        _capability("grok-imagine-video", lane="grok_imagine_video"),
        _capability("latentsync-1.6", lane="grok_lipsync"),
        _capability(
            "infinitetalk",
            lane="infinite_talk",
            promotion=infinite_promotion,
        ),
    ]


def test_current_preferred_tts_capability_cannot_be_overwritten_by_unverified_backend() -> None:
    capabilities = _capabilities()
    capabilities.append(_capability("rtx5090-voice-tts", lane="tts", canary_passed=False))

    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities,
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )

    assert plan["ok"] is True
    assert plan["capability_bindings"]["tts"]["id"] == "edge"


def _candidate(
    candidate_id: str,
    *,
    lane: str,
    quality: float,
    state_hash: str = STATE_HASH,
    audio_hash: str = AUDIO_HASH,
    hard_override: dict[str, bool] | None = None,
) -> dict[str, object]:
    hard_checks = {
        "decode": True,
        "geometry": True,
        "duration": True,
        "identity": True,
        "wardrobe": True,
        "background": True,
        "props": True,
        "lip_target": True,
        "poison_frame": True,
        "unique": True,
        "continuity": True,
    }
    hard_checks.update(hard_override or {})
    return {
        "candidate_id": candidate_id,
        "lane": lane,
        "state_image_sha256": state_hash,
        "audio_sha256": audio_hash,
        "output_sha256": ("c" if lane == "infinite_talk" else "d") * 64,
        "model": "infinitetalk" if lane == "infinite_talk" else "grok+latentsync",
        "elapsed_sec": 12.5,
        "peak_vram_mb": 18000,
        "runtime_status": "succeeded",
        "hard_checks": hard_checks,
        "quality_scores": {
            "lip_sync": quality,
            "mouth_teeth_jaw": quality,
            "outside_face_preservation": quality,
            "expression": quality,
            "motion": quality,
            "camera": quality,
            "state_match": quality,
            "edit_continuity": quality,
        },
    }


def test_builds_audio_linked_primary_secondary_dag_and_shared_inputs() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        stage="pilot",
        now=NOW,
    )

    assert plan["ok"] is True
    assert [step["id"] for step in plan["dag"]["steps"]] == [
        "state_i2i",
        "tts",
        "primary_infinite_talk",
        "secondary_grok_imagine",
        "secondary_lipsync",
        "qa",
        "provisional_select",
        "human_approve",
        "promote",
    ]
    assert plan["dag"]["execution"] == "conditional_single_gpu"
    assert plan["candidates"][0]["state_image_sha256"] == STATE_HASH
    assert plan["candidates"][1]["state_image_sha256"] == STATE_HASH
    assert plan["candidates"][0]["audio_sha256"] == AUDIO_HASH
    assert plan["candidates"][1]["audio_sha256"] == AUDIO_HASH
    assert plan["selected_route"] == "infinite_talk"
    assert plan["route_policy"]["secondary"] == "grok_imagine_video_then_latentsync"
    assert plan["dag"]["steps"][3]["run_condition"] == (
        "when_explicit_secondary_or_primary_technical_failure"
    )
    assert plan["approval"]["status"] == "not_reviewed"
    assert plan["promotion"]["authorized"] is False


@pytest.mark.parametrize("stage", ["production", "final"])
def test_unpromoted_infinite_talk_fails_closed_outside_pilot(stage: str) -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(infinite_promotion="pilot"),
        gpu_state={"queue_known": True, "busy": False},
        stage=stage,
        now=NOW,
    )

    assert plan["ok"] is False
    assert "DIALOGUE_ROUTE_NOT_PROMOTED" in {issue["code"] for issue in plan["issues"]}


def test_explicit_grok_route_requires_and_selects_audio_linked_secondary() -> None:
    shot = {**_shot(), "dialogue_motion_route": "grok_imagine_video"}
    plan = build_dialogue_competition_plan(
        shot,
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        stage="production",
        now=NOW,
    )

    assert plan["ok"] is True
    assert plan["selected_route"] == "grok_imagine_video"
    assert plan["candidates"][1]["audio_link"] == "latentsync_post_process"
    assert plan["candidates"][1]["production_eligible"] is True


def test_stale_capability_and_busy_or_unknown_gpu_fail_closed() -> None:
    stale = _capabilities()
    stale[4]["expires_at"] = "2026-07-29T11:59:59+00:00"
    stale_plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=stale,
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    busy_plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": True},
        now=NOW,
    )
    unknown_plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": False, "busy": False},
        now=NOW,
    )

    assert "CAPABILITY_STALE" in {issue["code"] for issue in stale_plan["issues"]}
    assert "GPU_BUSY" in {issue["code"] for issue in busy_plan["issues"]}
    assert "GPU_QUEUE_UNKNOWN" in {issue["code"] for issue in unknown_plan["issues"]}


def test_quality_or_identity_rejection_cannot_activate_grok_secondary() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    result = rank_dialogue_candidates(
        plan,
        [
            _candidate(
                "infinite-a",
                lane="infinite_talk",
                quality=0.99,
                hard_override={"identity": False},
            ),
            _candidate("grok-b", lane="grok_imagine_video", quality=0.70),
        ],
    )

    assert result["ok"] is False
    assert result["provisional_selection"] is None
    rejected = {item["candidate_id"]: item for item in result["rejected"]}
    assert rejected["infinite-a"]["hard_failures"] == ["identity"]
    assert "ROUTE_NOT_ACTIVATED" in rejected["grok-b"]["hard_failures"]
    assert result["approved_candidate_id"] is None
    assert result["promotion"]["authorized"] is False


def test_candidate_hash_drift_is_a_hard_rejection() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    result = rank_dialogue_candidates(
        plan,
        [
            _candidate(
                "infinite-a",
                lane="infinite_talk",
                quality=0.95,
                state_hash="e" * 64,
            ),
            _candidate("grok-b", lane="grok_imagine_video", quality=0.75),
        ],
    )

    rejected = {item["candidate_id"]: item for item in result["rejected"]}
    assert "STATE_HASH_MISMATCH" in rejected["infinite-a"]["hard_failures"]
    assert result["provisional_selection"] is None
    assert "ROUTE_NOT_ACTIVATED" in rejected["grok-b"]["hard_failures"]


def test_classified_primary_technical_failure_activates_grok_secondary() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    failed_primary = _candidate(
        "infinite-a",
        lane="infinite_talk",
        quality=0.0,
        hard_override={"decode": False},
    )
    failed_primary["runtime_status"] = "failed"
    failed_primary["technical_failure_code"] = "model_runtime_error"
    result = rank_dialogue_candidates(
        plan,
        [
            failed_primary,
            _candidate("grok-b", lane="grok_imagine_video", quality=0.75),
        ],
    )

    assert result["ok"] is True
    assert result["provisional_selection"]["candidate_id"] == "grok-b"


def test_technical_failure_cannot_mask_identity_drift_into_grok_fallback() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    failed_primary = _candidate(
        "infinite-a",
        lane="infinite_talk",
        quality=0.0,
        hard_override={"decode": False, "identity": False},
    )
    failed_primary["runtime_status"] = "failed"
    failed_primary["technical_failure_code"] = "model_runtime_error"
    result = rank_dialogue_candidates(
        plan,
        [
            failed_primary,
            _candidate("grok-b", lane="grok_imagine_video", quality=0.75),
        ],
    )

    assert result["ok"] is False
    assert result["provisional_selection"] is None
    rejected = {item["candidate_id"]: item for item in result["rejected"]}
    assert "ROUTE_NOT_ACTIVATED" in rejected["grok-b"]["hard_failures"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("human_quality_rejected", True),
        ("quality_rejected", True),
        ("review_status", "quality_rejected"),
        ("failure_class", "human_rejection"),
    ],
)
def test_technical_failure_cannot_mask_quality_rejection_into_grok_fallback(
    field: str,
    value: object,
) -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    failed_primary = _candidate(
        "infinite-a",
        lane="infinite_talk",
        quality=0.0,
        hard_override={"decode": False},
    )
    failed_primary["runtime_status"] = "failed"
    failed_primary["technical_failure_code"] = "timeout"
    failed_primary[field] = value
    result = rank_dialogue_candidates(
        plan,
        [
            failed_primary,
            _candidate("grok-b", lane="grok_imagine_video", quality=0.75),
        ],
    )

    assert result["ok"] is False
    assert result["provisional_selection"] is None
    rejected = {item["candidate_id"]: item for item in result["rejected"]}
    assert "ROUTE_NOT_ACTIVATED" in rejected["grok-b"]["hard_failures"]


def test_provisional_winner_requires_full_human_review_before_approval() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    ranked = rank_dialogue_candidates(
        plan,
        [
            _candidate("infinite-a", lane="infinite_talk", quality=0.90),
            _candidate("grok-b", lane="grok_imagine_video", quality=0.80),
        ],
    )

    rejected_review = approve_dialogue_candidate(
        ranked,
        reviewer="dex",
        watched_full=False,
        decision="approve",
    )
    approved = approve_dialogue_candidate(
        ranked,
        reviewer="dex",
        watched_full=True,
        decision="approve",
    )

    assert rejected_review["ok"] is False
    assert rejected_review["approval"]["status"] == "blocked"
    assert approved["ok"] is True
    assert approved["approval"]["status"] == "approved"
    assert approved["approved_candidate_id"] == "infinite-a"
    assert approved["promotion"]["authorized"] is True
    assert approved["provisional_selection"]["status"] == "pending_human_approval"


def test_validate_rejects_tampered_shared_input_contract() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    plan["candidates"][1]["audio_sha256"] = "f" * 64

    report = validate_dialogue_competition(plan)

    assert report["ok"] is False
    assert "CANDIDATE_AUDIO_HASH_MISMATCH" in {issue["code"] for issue in report["issues"]}


def test_validate_preserves_build_blockers_and_rejects_dag_dependency_tampering() -> None:
    blocked = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": True},
        now=NOW,
    )
    blocked_report = validate_dialogue_competition(blocked)
    assert blocked_report["ok"] is False
    assert "GPU_BUSY" in {issue["code"] for issue in blocked_report["issues"]}

    valid = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    valid["dag"]["steps"][-1]["depends_on"] = ["qa"]
    tampered_report = validate_dialogue_competition(valid)
    assert tampered_report["ok"] is False
    assert "DAG_INVALID" in {issue["code"] for issue in tampered_report["issues"]}

    policy_tampered = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    policy_tampered["route_policy"]["forbidden_secondary_triggers"] = []
    policy_report = validate_dialogue_competition(policy_tampered)
    assert policy_report["ok"] is False
    assert "ROUTE_POLICY_INVALID" in {issue["code"] for issue in policy_report["issues"]}


def test_human_approval_rejects_a_tampered_or_already_approved_result() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    ranked = rank_dialogue_candidates(
        plan,
        [
            _candidate("infinite-a", lane="infinite_talk", quality=0.90),
            _candidate("grok-b", lane="grok_imagine_video", quality=0.80),
        ],
    )
    ranked["provisional_selection"]["candidate_id"] = "injected-candidate"

    tampered = approve_dialogue_candidate(
        ranked,
        reviewer="dex",
        watched_full=True,
        decision="approve",
    )
    assert tampered["ok"] is False
    assert tampered["promotion"]["authorized"] is False
    assert "PROVISIONAL_SELECTION_INVALID" in {issue["code"] for issue in tampered["issues"]}

    clean_ranked = rank_dialogue_candidates(
        plan,
        [
            _candidate("infinite-a", lane="infinite_talk", quality=0.90),
            _candidate("grok-b", lane="grok_imagine_video", quality=0.80),
        ],
    )
    first = approve_dialogue_candidate(
        clean_ranked,
        reviewer="dex",
        watched_full=True,
        decision="approve",
    )
    second = approve_dialogue_candidate(
        first,
        reviewer="dex",
        watched_full=True,
        decision="approve",
    )
    assert second["ok"] is False
    assert second["promotion"]["authorized"] is False


def test_default_inputs_fail_closed_without_mutating_capabilities() -> None:
    missing = build_dialogue_competition_plan(_shot(), now=NOW)
    assert missing["ok"] is False
    assert {"CAPABILITIES_MISSING", "GPU_QUEUE_UNKNOWN"} <= {
        issue["code"] for issue in missing["issues"]
    }

    capabilities = _capabilities()
    original = [dict(item) for item in capabilities]
    build_dialogue_competition_plan(
        _shot(),
        capabilities=capabilities,
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    assert capabilities == original


def test_missing_receipt_evidence_is_hard_rejected() -> None:
    plan = build_dialogue_competition_plan(
        _shot(),
        capabilities=_capabilities(),
        gpu_state={"queue_known": True, "busy": False},
        now=NOW,
    )
    incomplete = _candidate("infinite-a", lane="infinite_talk", quality=0.99)
    incomplete.pop("output_sha256")
    result = rank_dialogue_candidates(
        plan,
        [
            incomplete,
            _candidate("grok-b", lane="grok_imagine_video", quality=0.70),
        ],
    )
    rejected = {item["candidate_id"]: item for item in result["rejected"]}
    assert "OUTPUT_SHA256_INVALID" in rejected["infinite-a"]["hard_failures"]
    assert result["provisional_selection"] is None
    assert "ROUTE_NOT_ACTIVATED" in rejected["grok-b"]["hard_failures"]
