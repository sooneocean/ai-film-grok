"""Native-audio dialogue motion plan: Grok Video + 5090 H3 (no post lipsync).

Policy (2026-08-05):
- Spoken on-camera shots generate motion+audio inside Grok Imagine Video or MiniMax H3.
- LatentSync / MuseTalk / InfiniteTalk / FRW lipsync are frozen out of the production DAG.
- Mix uses clip native audio (`prefer_native` / `use_clip_audio`); Edge TTS is caption/timing only.
"""

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
    "primary_grok_native": ["state_i2i"],
    "alt_h3_native": ["state_i2i"],
    "qa": ["primary_grok_native", "alt_h3_native"],
    "provisional_select": ["qa"],
    "human_approve": ["provisional_select"],
    "promote": ["human_approve"],
}
_STEP_CONDITIONS = {
    "state_i2i": "always",
    "primary_grok_native": "when_route_auto_or_grok",
    "alt_h3_native": "when_route_h3_or_primary_technical_failure",
    "qa": "after_active_route_succeeds",
    "provisional_select": "after_qa",
    "human_approve": "after_provisional_select",
    "promote": "after_human_approve",
}
_ROUTES = frozenset({"auto", "grok_imagine_video", "local_h3"})
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
# Frozen post tools — kept for docs/lint only; never wired into production DAG.
_FROZEN_LIPSYNC_TOOLS = (
    "latentsync",
    "musetalk",
    "infinite_talk",
    "fantasy_talking",
    "frw_lipsync",
    "wav2lip",
)


def _issues(plan: dict[str, Any]) -> list[dict[str, str]]:
    return plan.setdefault("issues", [])


def _capabilities(
    capabilities: list[dict[str, Any]], current: datetime
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    lanes: dict[str, dict[str, Any]] = {}
    for item in capabilities:
        if isinstance(item, dict) and str(item.get("id") or ""):
            copy = dict(item)
            result[str(copy["id"])] = copy
        else:
            continue
        try:
            valid = (
                datetime.fromisoformat(str(copy.get("expires_at")).replace("Z", "+00:00")) > current
            )
            verified = (
                datetime.fromisoformat(str(copy.get("verified_at")).replace("Z", "+00:00"))
                <= current
            )
        except (TypeError, ValueError):
            valid = False
            verified = False
        copy["_current"] = (
            valid
            and verified
            and copy.get("status") == "ready"
            and copy.get("canary_passed") is True
        )
        lane = str(copy.get("lane") or "")
        incumbent = lanes.get(lane)
        if lane and (
            incumbent is None
            or (copy["_current"] and not incumbent["_current"])
            or (
                copy["_current"] == incumbent["_current"]
                and int(copy.get("priority") or 0) > int(incumbent.get("priority") or 0)
            )
            or (
                copy["_current"] == incumbent["_current"]
                and int(copy.get("priority") or 0) == int(incumbent.get("priority") or 0)
                and str(copy["id"]) < str(incumbent["id"])
            )
        ):
            lanes[lane] = copy
    result.update(lanes)
    return result


def _resolve_requested_route(shot: dict[str, Any]) -> str:
    raw = str(shot.get("dialogue_motion_route") or "auto").strip().lower()
    # Legacy aliases map onto native-audio routes (lipsync stacks retired).
    if raw in {"infinite_talk", "latentsync", "musetalk", "frw_ltx", "cloud_dialogue_ltx"}:
        return "auto"
    if raw in {"h3", "comfy-h3", "local_dialogue_h3"}:
        return "local_h3"
    return raw if raw in _ROUTES else raw


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
    # Optional TTS hash for caption clock / ADR fallback — not the motion audio source.
    audio = str((shot.get("tts") or {}).get("audio_sha256") or "") or None
    restricted = bool(
        shot.get("restricted")
        or str(shot.get("heat_phase") or "").lower() in {"act", "climax", "bare"}
        or str(shot.get("wardrobe_state") or "").lower() in {"undressed", "bare"}
    )
    requested_route = _resolve_requested_route(shot)
    if requested_route == "auto" and restricted:
        selected_route = "local_h3"
    elif requested_route == "auto":
        selected_route = "grok_imagine_video"
    else:
        selected_route = requested_route

    plan: dict[str, Any] = {
        "schema_version": 2,
        "kind": "dialogue-competition",
        "policy": "native_audio_grok_h3_v1",
        "shot_id": shot.get("id"),
        "stage": stage,
        "route_policy": {
            "requested": str(shot.get("dialogue_motion_route") or "auto"),
            "primary": "grok_imagine_video",
            "secondary": "local_h3_native",
            "secondary_trigger": [
                "explicit_shot_route",
                "restricted_content",
                "classified_primary_technical_failure",
            ],
            "forbidden_secondary_triggers": [
                "human_quality_rejection",
                "unknown_error",
                "identity_drift",
            ],
            "audio_clock": "native_clip_audio",
            "audio_policy": "prefer_native",
            "lipsync_post": "frozen",
            "frozen_tools": list(_FROZEN_LIPSYNC_TOOLS),
            "storyboard_source": "approved_performance_state",
            "tts_role": "caption_timing_optional",
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
                "lane": "grok_imagine_video",
                "candidate_id": f"{shot.get('id')}__grok_imagine_video",
                "priority": "primary",
                "motion_method": "image_to_video_native_audio",
                "audio_link": "prefer_native_clip_audio",
                "state_image_sha256": state,
                "audio_sha256": audio,
            },
            {
                "lane": "local_h3",
                "candidate_id": f"{shot.get('id')}__local_h3",
                "priority": "secondary",
                "motion_method": "h3_i2v_or_r2v_native_audio",
                "audio_link": "prefer_native_clip_audio",
                "state_image_sha256": state,
                "audio_sha256": audio,
            },
        ],
        "shared_inputs": {
            "state_image_sha256": state,
            "audio_sha256": audio,
            "performance_intent": shot.get("performance_intent"),
            "spoken_text": shot.get("spoken_text") or shot.get("dialogue"),
        },
        "approval": {"status": "not_reviewed"},
        "approved_candidate_id": None,
        "promotion": {"authorized": False},
        "selected_route": selected_route,
    }
    if invalid_now:
        _issues(plan).append({"code": "NOW_INVALID", "message": "now must be timezone-aware"})
    if capabilities_missing:
        _issues(plan).append(
            {"code": "CAPABILITIES_MISSING", "message": "capabilities must be explicit"}
        )
    if stage not in {"pilot", "production", "final"}:
        _issues(plan).append({"code": "STAGE_INVALID", "message": "unsupported stage"})
    if requested_route not in _ROUTES:
        _issues(plan).append(
            {
                "code": "DIALOGUE_MOTION_ROUTE_INVALID",
                "message": "route must be auto, grok_imagine_video or local_h3",
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
    if not _SHA256.fullmatch(state):
        _issues(plan).append({"code": "STATE_HASH_INVALID", "message": "state hash is invalid"})
    # TTS is optional: only validate language when a final TTS receipt is present.
    tts = shot.get("tts") if isinstance(shot.get("tts"), dict) else {}
    if tts.get("status") == "final":
        tts_lang = str(tts.get("language") or "zh").strip().lower()
        if tts_lang not in {"zh", "cn", "chinese", "zh-cn", "zh_cn"}:
            _issues(plan).append(
                {"code": "TTS_LANGUAGE_INVALID", "message": "TTS must be Chinese (ja retired)"}
            )
        if audio and not _SHA256.fullmatch(str(audio)):
            _issues(plan).append(
                {"code": "AUDIO_HASH_INVALID", "message": "optional TTS hash is invalid"}
            )

    caps = _capabilities(capabilities or [], current)
    aliases = {
        "state_i2i": "qwen-image-i2i",
        "tts": "edge",
        "grok_imagine_video": "grok-imagine-video",
        "local_h3": "comfy-h3",
    }
    selected = {
        lane: caps.get(lane) or caps.get(capability_id, {})
        for lane, capability_id in aliases.items()
    }
    required_lanes = {"state_i2i"}
    if selected_route == "grok_imagine_video":
        required_lanes.add("grok_imagine_video")
    elif selected_route == "local_h3":
        required_lanes.add("local_h3")
    else:
        required_lanes.add("grok_imagine_video")
    stale_lanes = sorted(lane for lane in required_lanes if not selected[lane].get("_current"))
    if stale_lanes:
        _issues(plan).append(
            {
                "code": "CAPABILITY_STALE",
                "message": f"required capability is stale: {', '.join(stale_lanes)}",
            }
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
    grok_promotion = str(selected["grok_imagine_video"].get("promotion") or "").lower()
    h3_promotion = str(selected["local_h3"].get("promotion") or "").lower()
    plan["candidates"][0].update(
        {
            "models": [selected["grok_imagine_video"].get("model")],
            "pilot_only": grok_promotion not in {"production", "final", ""},
            "production_eligible": grok_promotion in {"production", "final", ""}
            or bool(selected["grok_imagine_video"].get("_current")),
        }
    )
    # Empty promotion on current-ready cloud Grok is treated production-eligible
    # (Grok Imagine is the bulk native-audio path).
    if selected["grok_imagine_video"].get("_current") and not grok_promotion:
        plan["candidates"][0]["production_eligible"] = True
        plan["candidates"][0]["pilot_only"] = False
    if selected["grok_imagine_video"].get("_current") and grok_promotion in {
        "production",
        "final",
        "pilot",
    }:
        # production_router stamps pilot for experimental; ready non-experimental is production
        if grok_promotion == "pilot":
            plan["candidates"][0]["production_eligible"] = False
            plan["candidates"][0]["pilot_only"] = True
        else:
            plan["candidates"][0]["production_eligible"] = True
            plan["candidates"][0]["pilot_only"] = False
    plan["candidates"][1].update(
        {
            "models": [selected["local_h3"].get("model")],
            "pilot_only": h3_promotion not in {"production", "final"},
            "production_eligible": h3_promotion in {"production", "final"},
        }
    )
    if selected["local_h3"].get("_current") and h3_promotion in {"production", "final", ""}:
        plan["candidates"][1]["production_eligible"] = True
        plan["candidates"][1]["pilot_only"] = False
    if selected["local_h3"].get("_current") and not h3_promotion:
        plan["candidates"][1]["production_eligible"] = True
        plan["candidates"][1]["pilot_only"] = False

    plan["secondary_available"] = bool(selected["local_h3"].get("_current"))
    # GPU is only hard for local H3 path (5090). Grok cloud does not need comfy queue.
    if selected_route == "local_h3":
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
    requested_route = str(route_policy.get("requested") or "auto")
    if requested_route in {"infinite_talk", "latentsync", "musetalk", "frw_ltx", "cloud_dialogue_ltx"}:
        expected_selected = plan.get("selected_route")
    elif requested_route == "local_h3":
        expected_selected = "local_h3"
    elif requested_route == "grok_imagine_video":
        expected_selected = "grok_imagine_video"
    else:
        expected_selected = plan.get("selected_route")
    if (
        route_policy.get("primary") != "grok_imagine_video"
        or route_policy.get("secondary") != "local_h3_native"
        or route_policy.get("audio_clock") != "native_clip_audio"
        or route_policy.get("lipsync_post") != "frozen"
        or route_policy.get("forbidden_secondary_triggers")
        != ["human_quality_rejection", "unknown_error", "identity_drift"]
        or (
            expected_selected is not None
            and plan.get("selected_route") != expected_selected
            and requested_route in _ROUTES
        )
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
    } != {"grok_imagine_video", "local_h3"}:
        issues.append(
            {
                "code": "CANDIDATE_LANES_INVALID",
                "message": "grok_imagine_video and local_h3 candidate lanes are required",
            }
        )
        candidates = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("state_image_sha256") != candidates[0].get("state_image_sha256"):
            issues.append(
                {"code": "CANDIDATE_STATE_HASH_MISMATCH", "message": "candidate state input drift"}
            )
        # audio_sha256 may be None (native path); when set, both candidates must match.
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
        != {"grok_imagine_video", "local_h3"}
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
    primary_lane = (
        "local_h3" if plan.get("selected_route") == "local_h3" else "grok_imagine_video"
    )
    alt_lane = "grok_imagine_video" if primary_lane == "local_h3" else "local_h3"
    primary_result = next(
        (item for item in candidates if item.get("lane") == primary_lane),
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
            lane == alt_lane
            and selected_route == primary_lane
            and primary_failed_technically
        )
        if not route_activated:
            failures.append("ROUTE_NOT_ACTIVATED")
        if candidate.get("state_image_sha256") != reference.get("state_image_sha256"):
            failures.append("STATE_HASH_MISMATCH")
        ref_audio = reference.get("audio_sha256")
        cand_audio = candidate.get("audio_sha256")
        if ref_audio and cand_audio and cand_audio != ref_audio:
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
        # peak_vram optional for cloud Grok (no local VRAM receipt).
        peak = candidate.get("peak_vram_mb")
        if lane == "local_h3" and (
            isinstance(peak, bool)
            or not isinstance(peak, (int, float))
            or peak <= 0
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
        and (
            not result.get("shared_inputs", {}).get("audio_sha256")
            or candidate.get("audio_sha256") == result.get("shared_inputs", {}).get("audio_sha256")
        )
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
