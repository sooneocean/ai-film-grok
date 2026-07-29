"""Fail-closed audio-linked motion plan for one dialogue performance shot."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from typing import Any

_HARD_CHECKS = (
    "decode",
    "geometry",
    "duration",
    "identity",
    "wardrobe",
    "background",
    "props",
    "lip_target",
    "poison_frame",
    "unique",
    "continuity",
)
_QUALITY_KEYS = (
    "lip_sync",
    "mouth_teeth_jaw",
    "outside_face_preservation",
    "expression",
    "motion",
    "camera",
    "state_match",
    "edit_continuity",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DEPENDENCIES = {
    "state_i2i": [],
    "tts": ["state_i2i"],
    "primary_infinite_talk": ["tts"],
    "secondary_grok_imagine": ["tts"],
    "secondary_lipsync": ["secondary_grok_imagine"],
    "qa": ["primary_infinite_talk", "secondary_lipsync"],
    "provisional_select": ["qa"],
    "human_approve": ["provisional_select"],
    "promote": ["human_approve"],
}
_STEP_CONDITIONS = {
    "state_i2i": "always",
    "tts": "always",
    "primary_infinite_talk": "when_route_auto_or_infinite_talk",
    "secondary_grok_imagine": "when_explicit_secondary_or_primary_technical_failure",
    "secondary_lipsync": "when_secondary_grok_imagine_succeeds",
    "qa": "after_active_route_succeeds",
    "provisional_select": "after_qa",
    "human_approve": "after_provisional_select",
    "promote": "after_human_approve",
}
_ROUTES = frozenset({"auto", "infinite_talk", "grok_imagine_video"})
_TECHNICAL_FAILURE_CODES = frozenset(
    {
        "provider_unavailable",
        "timeout",
        "queue_submission_failed",
        "model_runtime_error",
    }
)
_SECONDARY_BLOCKING_PRIMARY_FAILURES = frozenset(
    {
        "geometry",
        "identity",
        "wardrobe",
        "background",
        "props",
        "lip_target",
        "poison_frame",
        "unique",
        "continuity",
    }
)


def _issues(plan: dict[str, Any]) -> list[dict[str, str]]:
    return plan.setdefault("issues", [])


def _capabilities(
    capabilities: list[dict[str, Any]], current: datetime
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in capabilities:
        if isinstance(item, dict) and str(item.get("id") or ""):
            copy = dict(item)
            result[str(copy["id"])] = copy
            lane = str(copy.get("lane") or "")
            if lane:
                result[lane] = copy
    for item in {id(item): item for item in result.values()}.values():
        try:
            valid = (
                datetime.fromisoformat(str(item.get("expires_at")).replace("Z", "+00:00")) > current
            )
            verified = (
                datetime.fromisoformat(str(item.get("verified_at")).replace("Z", "+00:00"))
                <= current
            )
        except (TypeError, ValueError):
            valid = False
            verified = False
        item["_current"] = (
            valid
            and verified
            and item.get("status") == "ready"
            and item.get("canary_passed") is True
        )
    return result


def build_dialogue_competition_plan(
    shot: dict[str, Any],
    capabilities: list[dict[str, Any]] | None = None,
    gpu_state: dict[str, Any] | None = None,
    stage: str = "pilot",
    *,
    now: str | None = None,
) -> dict[str, Any]:
    capabilities_missing = not isinstance(capabilities, list)
    gpu_state = gpu_state if isinstance(gpu_state, dict) else {}
    try:
        current = datetime.fromisoformat(
            (now or datetime.now(UTC).isoformat()).replace("Z", "+00:00")
        )
        if current.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        current = datetime.now(UTC)
        invalid_now = True
    else:
        invalid_now = False
    state = str((shot.get("performance_state") or {}).get("image_sha256") or "")
    audio = str((shot.get("tts") or {}).get("audio_sha256") or "")
    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "dialogue-competition",
        "shot_id": shot.get("id"),
        "stage": stage,
        "route_policy": {
            "requested": str(shot.get("dialogue_motion_route") or "auto"),
            "primary": "infinite_talk",
            "secondary": "grok_imagine_video_then_latentsync",
            "secondary_trigger": [
                "explicit_shot_route",
                "classified_primary_technical_failure",
            ],
            "forbidden_secondary_triggers": [
                "human_quality_rejection",
                "unknown_error",
                "identity_drift",
            ],
            "audio_clock": "final_tts",
            "storyboard_source": "approved_performance_state",
        },
        "issues": [],
        "dag": {
            "execution": "conditional_single_gpu",
            "steps": [
                {
                    "id": step,
                    "depends_on": list(_DEPENDENCIES[step]),
                    "run_condition": _STEP_CONDITIONS[step],
                }
                for step in _DEPENDENCIES
            ],
        },
        "candidates": [
            {
                "lane": "infinite_talk",
                "candidate_id": f"{shot.get('id')}__infinite_talk",
                "priority": "primary",
                "motion_method": "face_animation_to_audio",
                "audio_link": "native_audio_conditioning",
                "state_image_sha256": state,
                "audio_sha256": audio,
            },
            {
                "lane": "grok_imagine_video",
                "candidate_id": f"{shot.get('id')}__grok_imagine_video",
                "priority": "secondary",
                "motion_method": "image_to_video_then_video_lip_sync",
                "audio_link": "latentsync_post_process",
                "state_image_sha256": state,
                "audio_sha256": audio,
            },
        ],
        "shared_inputs": {
            "state_image_sha256": state,
            "audio_sha256": audio,
            "performance_intent": shot.get("performance_intent"),
        },
        "approval": {"status": "not_reviewed"},
        "approved_candidate_id": None,
        "promotion": {"authorized": False},
    }
    if invalid_now:
        _issues(plan).append({"code": "NOW_INVALID", "message": "now must be timezone-aware"})
    if capabilities_missing:
        _issues(plan).append(
            {"code": "CAPABILITIES_MISSING", "message": "capabilities must be explicit"}
        )
    if stage not in {"pilot", "production", "final"}:
        _issues(plan).append({"code": "STAGE_INVALID", "message": "unsupported stage"})
    requested_route = str(shot.get("dialogue_motion_route") or "auto")
    if requested_route not in _ROUTES:
        _issues(plan).append(
            {
                "code": "DIALOGUE_MOTION_ROUTE_INVALID",
                "message": "route must be auto, infinite_talk or grok_imagine_video",
            }
        )
    if shot.get("shot_type") != "speaking":
        _issues(plan).append({"code": "SHOT_NOT_SPEAKING", "message": "shot must be speaking"})
    if not shot.get("id") or not shot.get("speaker") or not shot.get("performance_intent"):
        _issues(plan).append(
            {"code": "SHOT_CONTRACT_INCOMPLETE", "message": "speaking shot metadata is incomplete"}
        )
    if (shot.get("performance_state") or {}).get("status") != "approved":
        _issues(plan).append({"code": "STATE_NOT_APPROVED", "message": "state is not approved"})
    if (shot.get("tts") or {}).get("status") != "final":
        _issues(plan).append({"code": "TTS_NOT_FINAL", "message": "TTS is not final"})
    if (shot.get("tts") or {}).get("language") != "ja":
        _issues(plan).append({"code": "TTS_LANGUAGE_INVALID", "message": "TTS must be Japanese"})
    if not _SHA256.fullmatch(state):
        _issues(plan).append({"code": "STATE_HASH_INVALID", "message": "state hash is invalid"})
    if not _SHA256.fullmatch(audio):
        _issues(plan).append({"code": "AUDIO_HASH_INVALID", "message": "audio hash is invalid"})
    caps = _capabilities(capabilities or [], current)
    aliases = {
        "state_i2i": "qwen-image-i2i",
        "tts": "edge-ja",
        "infinite_talk": "infinitetalk",
        "grok_imagine_video": "grok-imagine-video",
        "grok_lipsync": "latentsync-1.6",
    }
    selected = {
        lane: caps.get(lane) or caps.get(capability_id, {})
        for lane, capability_id in aliases.items()
    }
    required_lanes = {"state_i2i", "tts"}
    if requested_route in {"auto", "infinite_talk"}:
        required_lanes.add("infinite_talk")
    if requested_route == "grok_imagine_video":
        required_lanes.update({"grok_imagine_video", "grok_lipsync"})
    if any(not selected[lane].get("_current") for lane in required_lanes):
        _issues(plan).append(
            {"code": "CAPABILITY_STALE", "message": "required capability is stale"}
        )
    plan["capability_bindings"] = {
        lane: {
            "id": capability.get("id"),
            "model": capability.get("model"),
            "promotion": capability.get("promotion"),
            "expires_at": capability.get("expires_at"),
        }
        for lane, capability in selected.items()
    }
    infinite_promotion = str(selected["infinite_talk"].get("promotion") or "").lower()
    grok_promotion = str(selected["grok_imagine_video"].get("promotion") or "").lower()
    lipsync_promotion = str(selected["grok_lipsync"].get("promotion") or "").lower()
    plan["candidates"][0].update(
        {
            "models": [selected["infinite_talk"].get("model")],
            "pilot_only": infinite_promotion not in {"production", "final"},
            "production_eligible": infinite_promotion in {"production", "final"},
        }
    )
    plan["candidates"][1].update(
        {
            "models": [
                selected["grok_imagine_video"].get("model"),
                selected["grok_lipsync"].get("model"),
            ],
            "pilot_only": any(
                promotion not in {"production", "final"}
                for promotion in (grok_promotion, lipsync_promotion)
            ),
            "production_eligible": all(
                promotion in {"production", "final"}
                for promotion in (grok_promotion, lipsync_promotion)
            ),
        }
    )
    plan["selected_route"] = (
        "grok_imagine_video" if requested_route == "grok_imagine_video" else "infinite_talk"
    )
    plan["secondary_available"] = all(
        selected[lane].get("_current") for lane in ("grok_imagine_video", "grok_lipsync")
    )
    if not gpu_state.get("queue_known"):
        _issues(plan).append({"code": "GPU_QUEUE_UNKNOWN", "message": "GPU queue is unknown"})
    elif gpu_state.get("busy"):
        _issues(plan).append({"code": "GPU_BUSY", "message": "GPU is busy"})
    selected_production_eligible = next(
        (
            candidate["production_eligible"]
            for candidate in plan["candidates"]
            if candidate["lane"] == plan["selected_route"]
        ),
        False,
    )
    if stage in {"production", "final"} and not selected_production_eligible:
        _issues(plan).append(
            {
                "code": "DIALOGUE_ROUTE_NOT_PROMOTED",
                "message": "selected dialogue motion route is pilot-only",
            }
        )
    plan["ok"] = not plan["issues"]
    return plan


def validate_dialogue_competition(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = list(plan.get("issues") or [])
    route_policy = plan.get("route_policy") or {}
    requested_route = route_policy.get("requested")
    expected_selected = (
        "grok_imagine_video" if requested_route == "grok_imagine_video" else "infinite_talk"
    )
    if (
        requested_route not in _ROUTES
        or route_policy.get("primary") != "infinite_talk"
        or route_policy.get("secondary") != "grok_imagine_video_then_latentsync"
        or route_policy.get("secondary_trigger")
        != ["explicit_shot_route", "classified_primary_technical_failure"]
        or route_policy.get("forbidden_secondary_triggers")
        != ["human_quality_rejection", "unknown_error", "identity_drift"]
        or plan.get("selected_route") != expected_selected
    ):
        issues.append(
            {
                "code": "ROUTE_POLICY_INVALID",
                "message": "dialogue route policy was modified",
            }
        )
    candidates = plan.get("candidates") if isinstance(plan.get("candidates"), list) else []
    if len(candidates) != 2 or {
        candidate.get("lane") for candidate in candidates if isinstance(candidate, dict)
    } != {"infinite_talk", "grok_imagine_video"}:
        issues.append(
            {"code": "CANDIDATE_LANES_INVALID", "message": "both candidate lanes are required"}
        )
        candidates = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("state_image_sha256") != candidates[0].get("state_image_sha256"):
            issues.append(
                {"code": "CANDIDATE_STATE_HASH_MISMATCH", "message": "candidate state input drift"}
            )
        if candidate.get("audio_sha256") != candidates[0].get("audio_sha256"):
            issues.append(
                {"code": "CANDIDATE_AUDIO_HASH_MISMATCH", "message": "candidate audio input drift"}
            )
    steps = (plan.get("dag") or {}).get("steps", [])
    if (
        (plan.get("dag") or {}).get("execution") != "conditional_single_gpu"
        or [step.get("id") for step in steps if isinstance(step, dict)] != list(_DEPENDENCIES)
        or any(
            step.get("depends_on") != _DEPENDENCIES.get(step.get("id"))
            or step.get("run_condition") != _STEP_CONDITIONS.get(step.get("id"))
            for step in steps
            if isinstance(step, dict)
        )
    ):
        issues.append({"code": "DAG_INVALID", "message": "serial DAG dependency was modified"})
    return {"ok": not issues, "issues": issues}


def rank_dialogue_candidates(
    plan: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    result = {
        **plan,
        "rejected": [],
        "approved_candidate_id": None,
        "promotion": {"authorized": False},
    }
    validation = validate_dialogue_competition(plan)
    if not validation["ok"] or plan.get("ok") is not True:
        result["ok"] = False
        result["issues"] = validation["issues"] or [
            {"code": "PLAN_NOT_READY", "message": "competition plan is blocked"}
        ]
        result["provisional_selection"] = None
        return result
    if (
        not isinstance(candidates, list)
        or len(candidates) != 2
        or {item.get("lane") for item in candidates if isinstance(item, dict)}
        != {"infinite_talk", "grok_imagine_video"}
    ):
        result["ok"] = False
        result["issues"] = [
            {
                "code": "CANDIDATE_RESULTS_INCOMPLETE",
                "message": "one result from each candidate lane is required",
            }
        ]
        result["provisional_selection"] = None
        return result
    primary_result = next(
        (item for item in candidates if item.get("lane") == "infinite_talk"),
        {},
    )
    primary_failure_code = str(primary_result.get("technical_failure_code") or "")
    primary_hard_checks = primary_result.get("hard_checks") or {}
    primary_quality_clean = all(
        primary_hard_checks.get(key) is True for key in _SECONDARY_BLOCKING_PRIMARY_FAILURES
    )
    primary_quality_rejected = (
        primary_result.get("human_quality_rejected") is True
        or primary_result.get("quality_rejected") is True
        or str(primary_result.get("review_status") or "").lower()
        in {"rejected", "quality_rejected", "human_rejected"}
        or str(primary_result.get("failure_class") or "").lower()
        in {"quality", "human_rejection", "identity_drift"}
    )
    primary_failed_technically = (
        primary_result.get("runtime_status") == "failed"
        and primary_failure_code in _TECHNICAL_FAILURE_CODES
        and primary_quality_clean
        and not primary_quality_rejected
    )
    valid: list[tuple[float, dict[str, Any]]] = []
    reference = (plan.get("candidates") or [{}])[0]
    for candidate in candidates:
        failures = [
            key for key in _HARD_CHECKS if (candidate.get("hard_checks") or {}).get(key) is not True
        ]
        lane = candidate.get("lane")
        selected_route = plan.get("selected_route")
        route_activated = lane == selected_route or (
            lane == "grok_imagine_video"
            and selected_route == "infinite_talk"
            and primary_failed_technically
        )
        if not route_activated:
            failures.append("ROUTE_NOT_ACTIVATED")
        if candidate.get("state_image_sha256") != reference.get("state_image_sha256"):
            failures.append("STATE_HASH_MISMATCH")
        if candidate.get("audio_sha256") != reference.get("audio_sha256"):
            failures.append("AUDIO_HASH_MISMATCH")
        if not _SHA256.fullmatch(str(candidate.get("output_sha256") or "")):
            failures.append("OUTPUT_SHA256_INVALID")
        if not str(candidate.get("model") or "").strip():
            failures.append("MODEL_MISSING")
        if (
            isinstance(candidate.get("elapsed_sec"), bool)
            or not isinstance(candidate.get("elapsed_sec"), (int, float))
            or candidate["elapsed_sec"] <= 0
        ):
            failures.append("ELAPSED_EVIDENCE_INVALID")
        if (
            isinstance(candidate.get("peak_vram_mb"), bool)
            or not isinstance(candidate.get("peak_vram_mb"), (int, float))
            or candidate["peak_vram_mb"] <= 0
        ):
            failures.append("VRAM_EVIDENCE_INVALID")
        scores = candidate.get("quality_scores") or {}
        for key in _QUALITY_KEYS:
            score = scores.get(key)
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                failures.append(f"QUALITY_{key.upper()}_INVALID")
        if failures:
            result["rejected"].append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "lane": candidate.get("lane"),
                    "hard_failures": failures,
                }
            )
            continue
        valid.append(
            (
                sum(float(scores.get(key, 0)) for key in _QUALITY_KEYS) / len(_QUALITY_KEYS),
                candidate,
            )
        )
    if valid:
        valid.sort(key=lambda item: (-item[0], str(item[1].get("candidate_id"))))
        winner = valid[0][1]
        result["provisional_selection"] = {
            "candidate_id": winner.get("candidate_id"),
            "lane": winner.get("lane"),
            "output_sha256": winner.get("output_sha256"),
            "status": "pending_human_approval",
            "automatic": True,
        }
        result["ranked_candidate_ids"] = [
            candidate.get("candidate_id") for _score, candidate in valid
        ]
        result["ranked_candidates"] = [
            {
                "candidate_id": candidate.get("candidate_id"),
                "lane": candidate.get("lane"),
                "output_sha256": candidate.get("output_sha256"),
                "state_image_sha256": candidate.get("state_image_sha256"),
                "audio_sha256": candidate.get("audio_sha256"),
                "model": candidate.get("model"),
                "elapsed_sec": candidate.get("elapsed_sec"),
                "peak_vram_mb": candidate.get("peak_vram_mb"),
                "quality_score": score,
            }
            for score, candidate in valid
        ]
    else:
        result["provisional_selection"] = None
    result["ok"] = result["provisional_selection"] is not None
    if not result["ok"]:
        result["issues"] = [
            {"code": "NO_ELIGIBLE_CANDIDATE", "message": "all candidates failed hard QA"}
        ]
    return result


def approve_dialogue_candidate(
    result: dict[str, Any], *, reviewer: str, watched_full: bool, decision: str
) -> dict[str, Any]:
    updated = {**result, "approval": {"status": "blocked"}, "promotion": {"authorized": False}}
    winner = result.get("provisional_selection") or {}
    if result.get("approval", {}).get("status") == "approved":
        updated["issues"] = [
            *result.get("issues", []),
            {"code": "ALREADY_APPROVED", "message": "result was already approved"},
        ]
        updated["ok"] = False
        return updated
    matching = [
        candidate
        for candidate in result.get("ranked_candidates", [])
        if isinstance(candidate, dict)
        and candidate.get("candidate_id") == winner.get("candidate_id")
        and candidate.get("lane") == winner.get("lane")
        and candidate.get("output_sha256") == winner.get("output_sha256")
        and candidate.get("state_image_sha256")
        == result.get("shared_inputs", {}).get("state_image_sha256")
        and candidate.get("audio_sha256") == result.get("shared_inputs", {}).get("audio_sha256")
    ]
    if len(matching) != 1:
        updated["issues"] = [
            *result.get("issues", []),
            {"code": "PROVISIONAL_SELECTION_INVALID", "message": "winner is not ranked"},
        ]
        updated["ok"] = False
        return updated
    if (
        decision != "approve"
        or not watched_full
        or not str(reviewer).strip()
        or not winner.get("candidate_id")
    ):
        updated["ok"] = False
        return updated
    updated["ok"] = True
    updated["approval"] = {
        "status": "approved",
        "reviewer": str(reviewer).strip(),
        "watched_full": True,
    }
    updated["approved_candidate_id"] = winner["candidate_id"]
    updated["promotion"] = {"authorized": True}
    return updated
