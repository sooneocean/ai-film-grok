#!/usr/bin/env python3
"""Deterministic, read-only shot routing over evidence-bearing capabilities."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from security_policy import SecurityPolicyError, validate_identifier
from util import canonical_json_sha256, read_json, sha256_file, write_json


class RouteExplainError(ValueError):
    """Typed error raised before a route plan can be computed."""


SELECTION_POLICY = [
    "hard_constraints",
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
    if not matches:
        raise RouteExplainError(f"SHOT_NOT_FOUND: {shot_id}")
    if len(matches) > 1:
        raise RouteExplainError(f"SHOT_ID_AMBIGUOUS: {shot_id}")
    return matches[0]


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
    film_lock = str(spec.get("i2v_provider") or "").strip().lower() if identity_lock else ""
    shot_lock = str(shot.get("i2v_provider") or shot.get("provider") or "").strip().lower()
    provider_lock = (
        shot_lock
        if shot_lock not in unlocked_values
        else film_lock
        if film_lock not in unlocked_values
        else ""
    )
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
    }


def _hard_rejections(
    capability: dict[str, Any],
    intent: dict[str, Any],
    *,
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
    return reasons


def _rank(capability: dict[str, Any], intent: dict[str, Any]) -> tuple[int, int, int, int]:
    roles = capability.get("shot_roles") or []
    role_affinity = 2 if roles == [intent["shot_role"]] else 1
    return (
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

    viable: list[tuple[tuple[int, int, int, int], str, dict[str, Any]]] = []
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
                "quality_floor": int(selected_raw.get("quality_floor") or 0),
                "quality_score": int(selected_raw.get("quality_score") or 0),
                "role_affinity": _rank(selected_raw, intent)[2],
                "priority": int(selected_raw.get("priority") or 0),
            },
            "requires_human_approval": bool(
                selected_raw.get("experimental") or selected_raw.get("human_approval_required")
            ),
        }

    rejected.sort(key=lambda item: str(item.get("capability_id") or ""))
    report = {
        "schema_version": 1,
        "kind": "ai-film-route-plan",
        "ok": selected is not None,
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
        "blocked_reason": None if selected is not None else "NO_VIABLE_CAPABILITY",
    }
    _validate_contract(report, "route-plan.schema.json", error_code="INVALID_ROUTE_PLAN")
    return report


def _execution_plan(route_plan: dict[str, Any], *, route_plan_sha256: str) -> dict[str, Any]:
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
