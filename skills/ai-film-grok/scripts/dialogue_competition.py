"""Fail-closed serial comparison plan for one dialogue performance shot."""

from __future__ import annotations

from datetime import datetime
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


def _issues(plan: dict[str, Any]) -> list[dict[str, str]]:
    return plan.setdefault("issues", [])


def _capabilities(capabilities: list[dict[str, Any]], now: str) -> dict[str, dict[str, Any]]:
    current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    result: dict[str, dict[str, Any]] = {}
    for item in capabilities:
        if isinstance(item, dict) and str(item.get("id") or ""):
            result[str(item["id"])] = item
    for item in result.values():
        try:
            valid = (
                datetime.fromisoformat(str(item.get("expires_at")).replace("Z", "+00:00")) > current
            )
        except ValueError:
            valid = False
        item["_current"] = (
            valid and item.get("status") == "ready" and item.get("canary_passed") is True
        )
    return result


def build_dialogue_competition_plan(
    shot: dict[str, Any],
    *,
    capabilities: list[dict[str, Any]],
    gpu_state: dict[str, Any],
    stage: str = "pilot",
    now: str,
) -> dict[str, Any]:
    state = str((shot.get("performance_state") or {}).get("image_sha256") or "")
    audio = str((shot.get("tts") or {}).get("audio_sha256") or "")
    plan: dict[str, Any] = {
        "schema_version": 1,
        "kind": "dialogue-competition",
        "shot_id": shot.get("id"),
        "stage": stage,
        "issues": [],
        "dag": {
            "execution": "serial_single_gpu",
            "steps": [
                {"id": step}
                for step in (
                    "state_i2i",
                    "tts",
                    "candidate_preservation",
                    "candidate_generative",
                    "qa",
                    "provisional_select",
                    "human_approve",
                    "promote",
                )
            ],
        },
        "candidates": [
            {"lane": "preservation", "state_image_sha256": state, "audio_sha256": audio},
            {"lane": "generative", "state_image_sha256": state, "audio_sha256": audio},
        ],
        "approval": {"status": "not_reviewed"},
        "approved_candidate_id": None,
        "promotion": {"authorized": False},
    }
    caps = _capabilities(capabilities, now)
    required = ("qwen-image-i2i", "edge-ja", "wan22-i2v", "latentsync-1.6", "infinitetalk")
    if any(not caps.get(name, {}).get("_current") for name in required):
        _issues(plan).append(
            {"code": "CAPABILITY_STALE", "message": "required capability is stale"}
        )
    if not gpu_state.get("queue_known"):
        _issues(plan).append({"code": "GPU_QUEUE_UNKNOWN", "message": "GPU queue is unknown"})
    elif gpu_state.get("busy"):
        _issues(plan).append({"code": "GPU_BUSY", "message": "GPU is busy"})
    if (
        stage in {"production", "final"}
        and caps.get("infinitetalk", {}).get("promotion") != "production"
    ):
        _issues(plan).append(
            {"code": "GENERATIVE_NOT_PROMOTED", "message": "generative lane is pilot-only"}
        )
    plan["ok"] = not plan["issues"]
    return plan


def validate_dialogue_competition(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = list(plan.get("issues") or [])
    candidates = plan.get("candidates") if isinstance(plan.get("candidates"), list) else []
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
    expected_dependencies = {
        "state_i2i": [],
        "tts": ["state_i2i"],
        "candidate_preservation": ["tts"],
        "candidate_generative": ["candidate_preservation"],
        "qa": ["candidate_generative"],
        "provisional_select": ["qa"],
        "human_approve": ["provisional_select"],
        "promote": ["human_approve"],
    }
    for step in (plan.get("dag") or {}).get("steps", []):
        if isinstance(step, dict) and step.get(
            "depends_on", expected_dependencies.get(step.get("id"), [])
        ) != expected_dependencies.get(step.get("id")):
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
    valid: list[tuple[float, dict[str, Any]]] = []
    reference = (plan.get("candidates") or [{}])[0]
    for candidate in candidates:
        failures = [
            key for key in _HARD_CHECKS if (candidate.get("hard_checks") or {}).get(key) is not True
        ]
        if candidate.get("state_image_sha256") != reference.get("state_image_sha256"):
            failures.append("STATE_HASH_MISMATCH")
        if candidate.get("audio_sha256") != reference.get("audio_sha256"):
            failures.append("AUDIO_HASH_MISMATCH")
        if failures:
            result["rejected"].append(
                {"candidate_id": candidate.get("candidate_id"), "hard_failures": failures}
            )
            continue
        scores = candidate.get("quality_scores") or {}
        valid.append(
            (
                sum(float(scores.get(key, 0)) for key in _QUALITY_KEYS) / len(_QUALITY_KEYS),
                candidate,
            )
        )
    if valid:
        winner = max(valid, key=lambda item: item[0])[1]
        result["provisional_selection"] = {
            "candidate_id": winner.get("candidate_id"),
            "status": "pending_human_approval",
        }
        result["ranked_candidate_ids"] = [
            candidate.get("candidate_id") for _score, candidate in valid
        ]
    else:
        result["provisional_selection"] = None
    result["ok"] = True
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
    if winner.get("candidate_id") not in result.get("ranked_candidate_ids", []):
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
