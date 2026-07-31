#!/usr/bin/env python3
"""Deterministic, read-only shot routing over evidence-bearing capabilities."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from security_policy import SecurityPolicyError, safe_existing_file, validate_identifier
from util import canonical_json_sha256, read_json, sha256_file, write_json


class RouteExplainError(ValueError):
    """Typed error raised before a route plan can be computed."""


SELECTION_POLICY = [
    "hard_constraints",
    "action_provider_priority",
    "quality_floor",
    "quality_score",
    "role_affinity",
    "priority",
    "stable_id",
]
_RESTRICTED_PHASES = frozenset({"foreplay", "act", "climax", "afterglow"})
_RESTRICTED_WARDROBE = frozenset({"partial", "undressed", "bare"})
_SUPPORTED_QUALITY_TIERS = frozenset({"draft", "select", "hero"})
_SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
_WAN_MODEL_IDENTITY_RE = re.compile(r"(?:^|/)wan(?:[0-9._-]|$)")
_MIN_LOCAL_RAM_BYTES = 12 * 1024**3
_MIN_LOCAL_VRAM_BYTES = 24 * 1024**3


def _dialogue_competition(
    base: Path,
    shot: dict[str, Any],
    capabilities: list[dict[str, Any]],
    *,
    current: datetime,
    stage: str,
) -> dict[str, Any] | None:
    if not (
        shot.get("lipsync") is True
        or shot.get("speaker_on_camera") is True
        or str(shot.get("screen_mode") or "") == "on_camera"
    ):
        return None
    from dialogue_competition import build_dialogue_competition_plan

    competition_capabilities: list[dict[str, Any]] = []
    for item in capabilities:
        if not isinstance(item, dict):
            continue
        value = dict(item)
        value["canary_passed"] = item.get("pilot_verified") is True
        value["promotion"] = "pilot" if item.get("experimental") is True else "production"
        identity = " ".join(str(item.get(key) or "").lower() for key in ("id", "provider", "model"))
        operations = set(item.get("operations") or [])
        if "image_to_image" in operations or (
            "qwen" in identity and ("image" in identity or "i2i" in identity)
        ):
            value["lane"] = "state_i2i"
        elif "text_to_speech" in operations or "edge" in identity:
            value["lane"] = "tts"
        elif "face_animation_to_audio" in operations or "infinitetalk" in identity:
            value["lane"] = "infinite_talk"
        elif "video_lip_sync" in operations or "latent" in identity:
            value["lane"] = "grok_lipsync"
        elif "image_to_video" in operations and "grok" in identity:
            value["lane"] = "grok_imagine_video"
        competition_capabilities.append(value)

    capacity = read_json(base / "receipts" / "comfy-capacity.json")
    gpu_state = {"queue_known": False, "busy": False}
    if isinstance(capacity, dict):
        queue_known = any(
            key in capacity
            for key in ("busy", "queue_busy", "queue_running", "queue_pending", "queue_known")
        )
        gpu_state = {
            "queue_known": bool(capacity.get("queue_known", queue_known)),
            "busy": bool(
                capacity.get("busy")
                or capacity.get("queue_busy")
                or capacity.get("queue_running")
                or capacity.get("queue_pending")
            ),
        }
    performance_state = (
        dict(shot.get("performance_state"))
        if isinstance(shot.get("performance_state"), dict)
        else {}
    )
    tts = dict(shot.get("tts")) if isinstance(shot.get("tts"), dict) else {}
    adapted = {
        **shot,
        "shot_type": "speaking",
        "performance_intent": shot.get("performance_intent")
        or {
            "emotion": performance_state.get("emotion"),
            "subtext": performance_state.get("subtext"),
            "gaze_target": performance_state.get("gaze_target"),
        },
        "performance_state": performance_state,
        "tts": tts,
    }
    return build_dialogue_competition_plan(
        adapted,
        capabilities=competition_capabilities,
        gpu_state=gpu_state,
        stage=stage,
        now=current.isoformat(),
    )


def _parse_time(value: object, *, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise RouteExplainError(f"INVALID_CAPABILITY_SNAPSHOT: {field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RouteExplainError(f"INVALID_CAPABILITY_SNAPSHOT: {field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise RouteExplainError(f"INVALID_CAPABILITY_SNAPSHOT: {field} must include a timezone")
    return parsed.astimezone(UTC)


def _validate_snapshot(snapshot: dict[str, Any]) -> None:
    schema = read_json(_SCHEMA_ROOT / "capability-snapshot.schema.json")
    if not isinstance(schema, dict):
        raise RouteExplainError("INVALID_CAPABILITY_SNAPSHOT: capability schema is unavailable")
    validator = jsonschema.Draft202012Validator(
        schema,
        format_checker=jsonschema.FormatChecker(),
    )
    errors = sorted(validator.iter_errors(snapshot), key=lambda item: list(item.path))
    if not errors:
        return
    error = errors[0]
    field = ".".join(str(part) for part in error.absolute_path) or "$"
    raise RouteExplainError(f"INVALID_CAPABILITY_SNAPSHOT: {field}: {error.message}")


def _validate_contract(value: dict[str, Any], schema_name: str, *, error_code: str) -> None:
    schema = read_json(_SCHEMA_ROOT / schema_name)
    if not isinstance(schema, dict):
        raise RouteExplainError(f"{error_code}: schema is unavailable")
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if not errors:
        return
    error = errors[0]
    field = ".".join(str(part) for part in error.absolute_path) or "$"
    raise RouteExplainError(f"{error_code}: {field}: {error.message}")


def _film_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for shot in spec.get("shots") or []:
        if isinstance(shot, dict):
            shots.append(shot)
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict):
                shots.append(shot)
    return shots


def _find_shot(spec: dict[str, Any], shot_id: str) -> dict[str, Any]:
    matches = [shot for shot in _film_shots(spec) if str(shot.get("id") or "") == shot_id]
    if matches:
        if len(matches) > 1:
            raise RouteExplainError(f"SHOT_ID_AMBIGUOUS: {shot_id}")
        return matches[0]
    broll_matches: list[dict[str, Any]] = []
    for parent in _film_shots(spec):
        for entry in parent.get("dialogue_broll") or []:
            if isinstance(entry, dict) and str(entry.get("id") or "") == shot_id:
                broll_matches.append(
                    {
                        **entry,
                        "_dialogue_broll_parent": str(parent.get("id") or ""),
                        "heat_phase": parent.get("heat_phase"),
                        "wardrobe_state": parent.get("wardrobe_state"),
                    }
                )
    if not broll_matches:
        raise RouteExplainError(f"SHOT_NOT_FOUND: {shot_id}")
    if len(broll_matches) > 1:
        raise RouteExplainError(f"SHOT_ID_AMBIGUOUS: {shot_id}")
    return broll_matches[0]


def build_shot_intent(
    spec: dict[str, Any],
    shot: dict[str, Any],
    *,
    quality_tier: str = "draft",
) -> dict[str, Any]:
    """Project an existing film-spec shot into routing hard constraints."""
    tier = str(quality_tier or "").strip().lower()
    if tier not in _SUPPORTED_QUALITY_TIERS:
        raise RouteExplainError("INVALID_QUALITY_TIER: expected one of draft, select, hero")
    shot_id = str(shot.get("id") or "").strip()
    if not shot_id:
        raise RouteExplainError("SHOT_ID_MISSING: film-spec shot has no id")
    role = str(shot.get("shot_role") or "hero").strip().lower()
    if role not in {"hero", "env", "bridge", "insert"}:
        role = "hero"
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    heat_phase = str(shot.get("heat_phase") or dsl.get("heat_phase") or "").lower()
    wardrobe = str(shot.get("wardrobe_state") or dsl.get("wardrobe_state") or "").lower()
    restricted = heat_phase in _RESTRICTED_PHASES or wardrobe in _RESTRICTED_WARDROBE
    identity_lock = role == "hero"
    operation = "image_to_video" if identity_lock else "text_to_video"
    unlocked_values = {"", "auto", "default", "unlocked"}
    film_lock = (
        str(spec.get("i2v_provider") or "").strip().lower()
        if identity_lock and spec.get("_i2v_provider_explicit") is True
        else ""
    )
    shot_lock = str(shot.get("i2v_provider") or shot.get("provider") or "").strip().lower()
    provider_lock = (
        shot_lock
        if shot_lock not in unlocked_values
        else film_lock
        if film_lock not in unlocked_values
        else ""
    )
    parent_shot_id = str(shot.get("_dialogue_broll_parent") or "").strip() or None
    broll_kind = str(shot.get("kind") or "").strip().lower() or None
    return {
        "schema_version": 1,
        "kind": "ai-film-shot-intent",
        "shot_id": shot_id,
        "shot_role": role,
        "operation": operation,
        "content_class": "restricted_local" if restricted else "general",
        "identity_lock": identity_lock,
        "continuity_required": str(dsl.get("chain_mode") or "").lower() == "continue",
        "quality_tier": tier,
        "provider_lock": provider_lock or None,
        "parent_shot_id": parent_shot_id,
        "broll_kind": broll_kind,
        "editorial_only": parent_shot_id is not None,
        "audio_policy": "carry_parent_dialogue" if parent_shot_id is not None else None,
    }


def _hard_rejections(
    capability: dict[str, Any],
    intent: dict[str, Any],
    *,
    base: Path,
    current: datetime,
    allow_experimental: bool,
) -> list[str]:
    reasons: list[str] = []
    status = str(capability.get("status") or "").lower()
    if status != "ready":
        reasons.append("CAPABILITY_NOT_READY")
    try:
        verified_at = _parse_time(capability.get("verified_at"), field="verified_at")
        expires_at = _parse_time(capability.get("expires_at"), field="expires_at")
        if verified_at > current:
            reasons.append("CAPABILITY_VERIFIED_IN_FUTURE")
        if expires_at <= current:
            reasons.append("CAPABILITY_STALE")
    except RouteExplainError:
        reasons.append("CAPABILITY_TIME_INVALID")
    if str(capability.get("authorization") or "").lower() != "ready":
        reasons.append("AUTHORIZATION_NOT_READY")
    if capability.get("pilot_verified") is not True:
        reasons.append("PILOT_NOT_VERIFIED")
    if capability.get("experimental") is True and not allow_experimental:
        reasons.append("EXPERIMENTAL_NOT_ALLOWED")
    domains = capability.get("domains")
    if isinstance(domains, list) and domains and "motion" not in domains:
        reasons.append("CAPABILITY_NOT_MOTION_ROUTE")
    if intent["operation"] not in set(capability.get("operations") or []):
        reasons.append("OPERATION_UNSUPPORTED")
    if intent["shot_role"] not in set(capability.get("shot_roles") or []):
        reasons.append("SHOT_ROLE_UNSUPPORTED")
    if intent["content_class"] not in set(capability.get("content_classes") or []):
        reasons.append("CONTENT_CLASS_UNSUPPORTED")
    if intent["identity_lock"] and capability.get("identity_lock_supported") is not True:
        reasons.append("IDENTITY_LOCK_UNSUPPORTED")
    provider_lock = str(intent.get("provider_lock") or "")
    if provider_lock and str(capability.get("provider") or "") != provider_lock:
        reasons.append("PROVIDER_LOCK_MISMATCH")
    supported_tiers = capability.get("quality_tiers")
    if isinstance(supported_tiers, list) and intent["quality_tier"] not in supported_tiers:
        reasons.append("QUALITY_TIER_UNSUPPORTED")
    lane = _action_lane(capability)
    if (
        intent["operation"] == "image_to_video"
        and lane == "other"
        and not intent.get("provider_lock")
    ):
        reasons.append("ACTION_PROVIDER_NOT_IN_CHAIN")
    if lane in {"frw-wan", "local"}:
        receipt = _bound_capability_receipt(base, capability)
        if receipt is None:
            reasons.append("CAPABILITY_EVIDENCE_UNBOUND")
        elif lane == "frw-wan" and not _frw_wan_receipt_ready(base, receipt):
            reasons.append("FRW_WAN_IDENTITY_UNVERIFIED")
        elif lane == "local" and not _local_capacity_receipt_ready(receipt):
            reasons.append("LOCAL_CAPACITY_UNVERIFIED")
    return reasons


def _action_lane(capability: dict[str, Any]) -> str:
    identity = " ".join(
        str(capability.get(key) or "").strip().lower() for key in ("id", "provider", "model")
    )
    provider = str(capability.get("provider") or "").strip().lower()
    if "frw" in identity and "ltx" in identity:
        return "frw-ltx"
    if provider == "grok" or "grok" in identity:
        return "grok"
    if "frw" in identity and _WAN_MODEL_IDENTITY_RE.search(
        str(capability.get("model") or "").strip().lower()
    ):
        return "frw-wan"
    if provider.startswith(("comfy", "local")) or "local" in identity:
        return "local"
    return "other"


def _bound_capability_receipt(base: Path, capability: dict[str, Any]) -> dict[str, Any] | None:
    path = capability.get("receipt_path")
    expected = capability.get("receipt_sha256")
    if not isinstance(path, str) or not isinstance(expected, str):
        return None
    try:
        receipt_path = safe_existing_file(base, path, field="capability receipt")
    except SecurityPolicyError:
        return None
    if sha256_file(receipt_path) != expected:
        return None
    receipt = read_json(receipt_path)
    return receipt if isinstance(receipt, dict) else None


def _receipt_output_is_bound(base: Path, receipt: dict[str, Any]) -> bool:
    output = receipt.get("output")
    if isinstance(output, dict):
        output = output.get("path")
    output = output or receipt.get("output_path")
    expected = receipt.get("output_sha256")
    if not isinstance(output, str) or not isinstance(expected, str):
        return False
    try:
        output_path = safe_existing_file(base, output, field="capability output")
    except SecurityPolicyError:
        return False
    return sha256_file(output_path) == expected


def _frw_wan_receipt_ready(base: Path, receipt: dict[str, Any]) -> bool:
    model = str(receipt.get("provider_model") or receipt.get("model") or "").strip().lower()
    return bool(
        receipt.get("ok") is True
        and _WAN_MODEL_IDENTITY_RE.search(model)
        and receipt.get("full_decode_ok") is True
        and receipt.get("human_review") == "approved"
        and _receipt_output_is_bound(base, receipt)
    )


def _local_capacity_receipt_ready(receipt: dict[str, Any]) -> bool:
    floors = receipt.get("floors") if isinstance(receipt.get("floors"), dict) else {}
    observed = receipt.get("observed") if isinstance(receipt.get("observed"), dict) else {}
    device = observed.get("device") if isinstance(observed.get("device"), dict) else {}
    queue = observed.get("queue") if isinstance(observed.get("queue"), dict) else {}
    ram_floor = floors.get("ram_free_bytes")
    vram_floor = floors.get("vram_free_bytes")
    ram_free = observed.get("ram_free_bytes")
    vram_free = device.get("vram_free_bytes")
    return bool(
        receipt.get("ok") is True
        and receipt.get("kind") == "comfy-submission-capacity"
        and isinstance(ram_floor, int)
        and isinstance(vram_floor, int)
        and isinstance(ram_free, int)
        and isinstance(vram_free, int)
        and ram_floor >= _MIN_LOCAL_RAM_BYTES
        and vram_floor >= _MIN_LOCAL_VRAM_BYTES
        and ram_free >= _MIN_LOCAL_RAM_BYTES
        and vram_free >= _MIN_LOCAL_VRAM_BYTES
        and ram_free >= ram_floor
        and vram_free >= vram_floor
        and queue.get("running") == 0
        and queue.get("pending") == 0
    )


def _action_provider_priority(capability: dict[str, Any]) -> int:
    return {
        "frw-ltx": 4,
        "grok": 3,
        "frw-wan": 2,
        "local": 1,
    }.get(_action_lane(capability), 0)


def _rank(capability: dict[str, Any], intent: dict[str, Any]) -> tuple[int, int, int, int, int]:
    roles = capability.get("shot_roles") or []
    role_affinity = 2 if roles == [intent["shot_role"]] else 1
    return (
        _action_provider_priority(capability),
        int(capability.get("quality_floor") or 0),
        int(capability.get("quality_score") or 0),
        role_affinity,
        int(capability.get("priority") or 0),
    )


def explain_route(
    root: Path | str,
    *,
    shot_id: str,
    capabilities_path: Path | str | None = None,
    quality_tier: str = "draft",
    allow_experimental: bool = False,
    now: str | None = None,
) -> dict[str, Any]:
    """Explain one route without probing, writing, submitting, or spending."""
    base = Path(root).expanduser().resolve()
    spec_path = base / "film-spec.json"
    spec = read_json(spec_path)
    if not isinstance(spec, dict):
        raise RouteExplainError(f"FILM_SPEC_MISSING: {spec_path}")
    shot = _find_shot(spec, str(shot_id).strip())
    intent = build_shot_intent(spec, shot, quality_tier=quality_tier)

    snapshot_path = (
        Path(capabilities_path).expanduser().resolve()
        if capabilities_path is not None
        else base / "receipts" / "capability-snapshot.json"
    )
    snapshot = read_json(snapshot_path)
    if not isinstance(snapshot, dict):
        raise RouteExplainError(f"CAPABILITY_SNAPSHOT_MISSING: {snapshot_path}")
    _validate_snapshot(snapshot)
    capabilities = snapshot.get("capabilities")
    assert isinstance(capabilities, list)
    capability_ids = [
        str(item.get("id") or "").strip()
        for item in capabilities
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    if len(capability_ids) != len(set(capability_ids)):
        raise RouteExplainError("INVALID_CAPABILITY_SNAPSHOT: duplicate capability id")
    current = _parse_time(now or datetime.now(UTC).isoformat(), field="now")

    viable: list[tuple[tuple[int, int, int, int, int], str, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for raw in capabilities:
        if not isinstance(raw, dict):
            rejected.append(
                {
                    "capability_id": None,
                    "provider": None,
                    "model": None,
                    "reasons": ["CAPABILITY_ENTRY_INVALID"],
                }
            )
            continue
        capability_id = str(raw.get("id") or "").strip()
        reasons = _hard_rejections(
            raw,
            intent,
            base=base,
            current=current,
            allow_experimental=allow_experimental,
        )
        projection = {
            "capability_id": capability_id or None,
            "provider": raw.get("provider"),
            "model": raw.get("model"),
        }
        if not capability_id:
            reasons.append("CAPABILITY_ID_MISSING")
        if reasons:
            rejected.append({**projection, "reasons": sorted(set(reasons))})
            continue
        viable.append((_rank(raw, intent), capability_id, raw))

    viable.sort(key=lambda item: item[1])
    viable.sort(key=lambda item: item[0], reverse=True)
    selected_raw = viable[0][2] if viable else None
    selected = None
    if selected_raw is not None:
        selected = {
            "capability_id": selected_raw["id"],
            "provider": selected_raw["provider"],
            "model": selected_raw["model"],
            "resource": selected_raw["resource"],
            "concurrency": selected_raw["concurrency"],
            "rank": {
                "action_provider_priority": _action_provider_priority(selected_raw),
                "quality_floor": int(selected_raw.get("quality_floor") or 0),
                "quality_score": int(selected_raw.get("quality_score") or 0),
                "role_affinity": _rank(selected_raw, intent)[3],
                "priority": int(selected_raw.get("priority") or 0),
            },
            "requires_human_approval": bool(
                selected_raw.get("experimental") or selected_raw.get("human_approval_required")
            ),
        }

    rejected.sort(key=lambda item: str(item.get("capability_id") or ""))
    competition = _dialogue_competition(
        base,
        shot,
        capabilities,
        current=current,
        stage={"draft": "pilot", "select": "production", "hero": "final"}[quality_tier],
    )
    if isinstance(competition, dict):
        bindings = competition.get("capability_bindings") or {}
        active_lanes = (
            ["grok_imagine_video", "grok_lipsync"]
            if competition.get("selected_route") == "grok_imagine_video"
            else ["infinite_talk"]
        )
        chain_ids = [
            str((bindings.get(lane) or {}).get("id") or "")
            for lane in active_lanes
            if str((bindings.get(lane) or {}).get("id") or "")
        ]
        active = next(
            (
                item
                for item in capabilities
                if isinstance(item, dict)
                and str(item.get("id") or "") == (chain_ids[0] if chain_ids else "")
            ),
            None,
        )
        if isinstance(active, dict):
            selected = {
                "capability_id": active["id"],
                "provider": active["provider"],
                "model": active["model"],
                "resource": active["resource"],
                "concurrency": active["concurrency"],
                "route_chain": chain_ids,
                "dialogue_motion_route": competition.get("selected_route"),
                "requires_human_approval": True,
            }
            rejected = [
                item for item in rejected if item.get("capability_id") not in set(chain_ids)
            ]
    route_ok = selected is not None and (competition is None or competition.get("ok") is True)
    report = {
        "schema_version": 1,
        "kind": "ai-film-route-plan",
        "ok": route_ok,
        "read_only": True,
        "auto_execute": False,
        "explained_at": current.isoformat(),
        "film_spec": {"path": str(spec_path), "sha256": sha256_file(spec_path)},
        "capability_snapshot": {
            "path": str(snapshot_path),
            "sha256": sha256_file(snapshot_path),
            "generated_at": snapshot.get("generated_at"),
        },
        "intent": intent,
        "selection_policy": SELECTION_POLICY,
        "selected": selected,
        "alternatives": [
            {
                "capability_id": raw["id"],
                "provider": raw["provider"],
                "model": raw["model"],
                "rank": list(rank),
            }
            for rank, _capability_id, raw in viable[1:]
        ],
        "rejected": rejected,
        "dialogue_competition": competition,
        "blocked_reason": (
            None
            if route_ok
            else "NO_VIABLE_CAPABILITY"
            if selected is None
            else "DIALOGUE_COMPETITION_BLOCKED"
        ),
    }
    _validate_contract(report, "route-plan.schema.json", error_code="INVALID_ROUTE_PLAN")
    return report


def _execution_plan(route_plan: dict[str, Any], *, route_plan_sha256: str) -> dict[str, Any]:
    competition = route_plan.get("dialogue_competition")
    intent = route_plan.get("intent")
    if isinstance(competition, dict):
        if not isinstance(intent, dict):
            raise RouteExplainError("INVALID_ROUTE_PLAN: intent is missing")
        shot_id = str(intent.get("shot_id") or "").strip()
        if not shot_id:
            raise RouteExplainError("INVALID_ROUTE_PLAN: shot id is missing")
        bindings = (
            competition.get("capability_bindings")
            if isinstance(competition.get("capability_bindings"), dict)
            else {}
        )
        step_bindings = {
            "state_i2i": "state_i2i",
            "tts": "tts",
            "primary_infinite_talk": "infinite_talk",
            "secondary_grok_imagine": "grok_imagine_video",
            "secondary_lipsync": "grok_lipsync",
            "qa": "dialogue-qa",
            "provisional_select": "dialogue-ranker",
            "human_approve": "human-review",
            "promote": "media-promotion",
        }
        resources = {
            "human_approve": "human_review",
            "provisional_select": "local_cpu",
            "qa": "local_cpu",
            "promote": "local_filesystem",
        }
        tasks: list[dict[str, Any]] = []
        task_ids: dict[str, str] = {}
        for step in (competition.get("dag") or {}).get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or "")
            binding_key = step_bindings.get(step_id, step_id)
            binding = bindings.get(binding_key)
            capability_id = (
                str(binding.get("id") or binding_key) if isinstance(binding, dict) else binding_key
            )
            task_id = f"route-{shot_id}-{step_id}"
            task_ids[step_id] = task_id
            depends_on = [
                task_ids[dependency]
                for dependency in step.get("depends_on") or []
                if dependency in task_ids
            ]
            task_key = canonical_json_sha256(
                {
                    "route_plan_sha256": route_plan_sha256,
                    "shot_id": shot_id,
                    "step": step_id,
                    "capability_id": capability_id,
                    "depends_on": depends_on,
                }
            )
            tasks.append(
                {
                    "id": task_id,
                    "shot_id": shot_id,
                    "capability_id": capability_id,
                    "resource": resources.get(step_id, "rtx5090_serial"),
                    "depends_on": depends_on,
                    "run_condition": step.get("run_condition", "always"),
                    "idempotency_key": task_key,
                    "status": "planned" if competition.get("ok") is True else "blocked",
                }
            )
        plan = {
            "schema_version": 1,
            "kind": "ai-film-execution-plan",
            "route_plan_sha256": route_plan_sha256,
            "authorized": False,
            "tasks": tasks,
        }
        _validate_contract(plan, "execution-plan.schema.json", error_code="INVALID_EXECUTION_PLAN")
        return plan

    selected = route_plan.get("selected")
    if not isinstance(selected, dict):
        plan = {
            "schema_version": 1,
            "kind": "ai-film-execution-plan",
            "route_plan_sha256": route_plan_sha256,
            "authorized": False,
            "tasks": [],
        }
        _validate_contract(plan, "execution-plan.schema.json", error_code="INVALID_EXECUTION_PLAN")
        return plan

    intent = route_plan.get("intent")
    if not isinstance(intent, dict):
        raise RouteExplainError("INVALID_ROUTE_PLAN: intent is missing")
    shot_id = str(intent.get("shot_id") or "").strip()
    capability_id = str(selected.get("capability_id") or "").strip()
    resource = str(selected.get("resource") or "").strip()
    if not shot_id or not capability_id or not resource:
        raise RouteExplainError("INVALID_ROUTE_PLAN: selected route is incomplete")
    task_key = canonical_json_sha256(
        {
            "route_plan_sha256": route_plan_sha256,
            "shot_id": shot_id,
            "capability_id": capability_id,
            "resource": resource,
        }
    )
    plan = {
        "schema_version": 1,
        "kind": "ai-film-execution-plan",
        "route_plan_sha256": route_plan_sha256,
        "authorized": False,
        "tasks": [
            {
                "id": f"route-{task_key[:16]}",
                "shot_id": shot_id,
                "capability_id": capability_id,
                "resource": resource,
                "depends_on": [],
                "run_condition": "always",
                "idempotency_key": task_key,
                "status": "planned",
            }
        ],
    }
    _validate_contract(plan, "execution-plan.schema.json", error_code="INVALID_EXECUTION_PLAN")
    return plan


def plan_route(
    root: Path | str,
    *,
    shot_id: str,
    capabilities_path: Path | str | None = None,
    quality_tier: str = "draft",
    allow_experimental: bool = False,
    now: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """Build a hash-bound, non-authorized execution plan without submitting work.

    The default is a pure preview.  ``write=True`` persists immutable-by-hash
    route/execution receipts, but never creates a media-queue job or authorizes
    a provider request.
    """
    base = Path(root).expanduser().resolve()
    route_plan = explain_route(
        base,
        shot_id=shot_id,
        capabilities_path=capabilities_path,
        quality_tier=quality_tier,
        allow_experimental=allow_experimental,
        now=now,
    )
    route_digest = canonical_json_sha256(route_plan)
    execution_plan = _execution_plan(route_plan, route_plan_sha256=route_digest)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-route-planning",
        "ok": route_plan["ok"],
        "read_only": not write,
        "auto_execute": False,
        "written": False,
        "route_plan": route_plan,
        "execution_plan": execution_plan,
        "receipts": None,
        "blocked_reason": route_plan["blocked_reason"],
    }
    if not write or route_plan["ok"] is not True:
        return report

    try:
        shot_component = validate_identifier(
            str(route_plan["intent"]["shot_id"]), field="route plan shot id"
        )
    except SecurityPolicyError as exc:
        raise RouteExplainError(f"INVALID_ROUTE_PLAN: {exc}") from exc
    route_path = base / "receipts" / "route-plans" / f"{shot_component}-{route_digest[:16]}.json"
    execution_path = (
        base / "receipts" / "execution-plans" / f"{shot_component}-{route_digest[:16]}.json"
    )
    write_json(route_path, route_plan)
    execution_plan = _execution_plan(route_plan, route_plan_sha256=sha256_file(route_path))
    write_json(execution_path, execution_plan)
    report.update(
        {
            "written": True,
            "execution_plan": execution_plan,
            "receipts": {
                "route_plan": str(route_path),
                "execution_plan": str(execution_path),
            },
        }
    )
    return report


def preflight_route_plan(
    root: Path | str,
    *,
    route_plan_path: Path | str,
    execution_plan_path: Path | str,
    now: str | None = None,
) -> dict[str, Any]:
    """Read current evidence before a human may authorize a planned route."""
    base = Path(root).expanduser().resolve()
    route_path = Path(route_plan_path).expanduser().resolve()
    execution_path = Path(execution_plan_path).expanduser().resolve()
    route_plan = read_json(route_path)
    execution_plan = read_json(execution_path)
    blockers: list[str] = []
    if not isinstance(route_plan, dict):
        blockers.append("ROUTE_PLAN_MISSING")
        route_plan = {}
    else:
        try:
            _validate_contract(
                route_plan, "route-plan.schema.json", error_code="INVALID_ROUTE_PLAN"
            )
        except RouteExplainError:
            blockers.append("ROUTE_PLAN_INVALID")
    if not isinstance(execution_plan, dict):
        blockers.append("EXECUTION_PLAN_MISSING")
        execution_plan = {}
    else:
        try:
            _validate_contract(
                execution_plan, "execution-plan.schema.json", error_code="INVALID_EXECUTION_PLAN"
            )
        except RouteExplainError:
            blockers.append("EXECUTION_PLAN_INVALID")

    if not blockers:
        if execution_plan.get("route_plan_sha256") != sha256_file(route_path):
            blockers.append("ROUTE_PLAN_HASH_MISMATCH")
        if execution_plan.get("authorized") is not False:
            blockers.append("EXECUTION_ALREADY_AUTHORIZED")
        tasks = execution_plan.get("tasks") or []
        if not tasks or any(
            task.get("status") != "planned" for task in tasks if isinstance(task, dict)
        ):
            blockers.append("EXECUTION_NOT_PLANNED")
        film_source = (
            route_plan.get("film_spec") if isinstance(route_plan.get("film_spec"), dict) else {}
        )
        snapshot_source = (
            route_plan.get("capability_snapshot")
            if isinstance(route_plan.get("capability_snapshot"), dict)
            else {}
        )
        film_path = Path(str(film_source.get("path") or "")).expanduser()
        snapshot_path = Path(str(snapshot_source.get("path") or "")).expanduser()
        if not film_path.is_file() or film_source.get("sha256") != sha256_file(film_path):
            blockers.append("FILM_SPEC_CHANGED")
        if not snapshot_path.is_file() or snapshot_source.get("sha256") != sha256_file(
            snapshot_path
        ):
            blockers.append("CAPABILITY_SNAPSHOT_CHANGED")
        if not blockers:
            intent = route_plan["intent"]
            current = explain_route(
                base,
                shot_id=str(intent["shot_id"]),
                capabilities_path=snapshot_path,
                quality_tier=str(intent["quality_tier"]),
                now=now,
            )
            selected = route_plan.get("selected") or {}
            latest = current.get("selected") or {}
            if current.get("ok") is not True or latest.get("capability_id") != selected.get(
                "capability_id"
            ):
                blockers.append("ROUTE_NO_LONGER_CURRENT")
            snapshot = read_json(snapshot_path) or {}
            capability = next(
                (
                    item
                    for item in snapshot.get("capabilities") or []
                    if isinstance(item, dict) and item.get("id") == selected.get("capability_id")
                ),
                {},
            )
            if capability.get("cost_state") not in {"known", "free_local"}:
                blockers.append("COST_STATE_UNKNOWN")
            queue = read_json(base / "receipts" / "media-queue.json") or {}
            jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
            budget = int((queue.get("policy") or {}).get("budget_units") or 20)
            if len(jobs) >= budget:
                blockers.append("QUEUE_BUDGET_EXHAUSTED")
            try:
                from production_gates import assert_pilot_allows_add

                assert_pilot_allows_add(
                    base,
                    shot_id=str(intent["shot_id"]),
                    existing_shot_ids={
                        str(item.get("shot_id")) for item in jobs if isinstance(item, dict)
                    },
                )
            except Exception:
                blockers.append("PILOT_GATE_BLOCKED")
    blockers = sorted(set(blockers))
    return {
        "schema_version": 1,
        "kind": "ai-film-route-preflight",
        "ok": not blockers,
        "read_only": True,
        "auto_execute": False,
        "authorized": False,
        "requires_human_authorization": True,
        "ready_for_human_authorization": not blockers,
        "route_plan": str(route_path),
        "execution_plan": str(execution_path),
        "blockers": blockers,
    }
