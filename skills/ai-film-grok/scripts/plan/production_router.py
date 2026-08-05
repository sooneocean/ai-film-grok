#!/usr/bin/env python3
"""Deterministic, read-only shot routing over evidence-bearing capabilities."""

from __future__ import annotations

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
# Hard difficulty: route to local H3 even when heat_phase was left blank.
_DIFFICULTY_COITUS = frozenset(
    {
        "deep_thrust",
        "internal_peak",
        "creampie_release",
        "creampie",
        "penetration",
        "union",
        "rhythm",
        "lock",
    }
)
_DIFFICULTY_SEX_ARC = frozenset(
    {
        "penetration",
        "climax_release",
        "climax",
        "deep_thrust",
        "internal_peak",
        "creampie",
    }
)
_L4_SIZES = frozenset({"l4", "ecu", "extreme_close", "extreme_closeup", "insert_l4"})
_SUPPORTED_QUALITY_TIERS = frozenset({"draft", "select", "hero"})
_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
_MIN_LOCAL_RAM_BYTES = 12 * 1024**3
_MIN_LOCAL_VRAM_BYTES = 24 * 1024**3


def _shot_difficulty_flags(shot: dict[str, Any], dsl: dict[str, Any]) -> list[str]:
    """Return difficulty reason codes that push a shot toward local H3."""
    flags: list[str] = []
    coitus = (
        str(shot.get("coitus_beat") or dsl.get("coitus_beat") or shot.get("coitus") or "")
        .strip()
        .lower()
    )
    if coitus in _DIFFICULTY_COITUS:
        flags.append(f"coitus_beat:{coitus}")
    sex_arc = str(shot.get("sex_arc_beat") or dsl.get("sex_arc_beat") or "").strip().lower()
    if sex_arc in _DIFFICULTY_SEX_ARC:
        flags.append(f"sex_arc_beat:{sex_arc}")
    camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    shot_size = (
        str(shot.get("shot_size") or dsl.get("shot_size") or camera.get("shot_size") or "")
        .strip()
        .lower()
    )
    contact = shot.get("contact") if shot.get("contact") is not None else dsl.get("contact")
    has_contact = contact is True or (
        isinstance(contact, str) and contact.strip().lower() not in {"", "none", "false", "0"}
    )
    if shot_size in _L4_SIZES and has_contact:
        flags.append(f"l4_contact:{shot_size}")
    sex_pose = str(shot.get("sex_pose") or dsl.get("sex_pose") or "").strip().lower()
    heat = str(shot.get("heat_phase") or dsl.get("heat_phase") or "").strip().lower()
    if (
        sex_pose
        and sex_pose not in {"none", "embrace", "hug", "kiss", "clothed"}
        and heat in _RESTRICTED_PHASES
    ):
        flags.append(f"sex_pose:{sex_pose}")
    try:
        duration = float(shot.get("duration_sec") or dsl.get("duration_sec") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration >= 8.0 and heat in {"act", "climax"}:
        flags.append(f"long_meat:{duration:g}s")
    if shot.get("force_local_h3") is True or str(shot.get("motion_lane") or "").lower() in {
        "local_h3",
        "comfy-h3",
        "h3",
    }:
        flags.append("explicit_local_h3")
    return flags


def classify_shot_content(
    shot: dict[str, Any],
    *,
    dsl: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify general vs restricted_local with heat/wardrobe + difficulty signals."""
    body = (
        dsl
        if isinstance(dsl, dict)
        else (shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {})
    )
    heat_phase = str(shot.get("heat_phase") or body.get("heat_phase") or "").lower()
    wardrobe = str(shot.get("wardrobe_state") or body.get("wardrobe_state") or "").lower()
    reasons: list[str] = []
    if heat_phase in _RESTRICTED_PHASES:
        reasons.append(f"heat_phase:{heat_phase}")
    if wardrobe in _RESTRICTED_WARDROBE:
        reasons.append(f"wardrobe:{wardrobe}")
    difficulty = _shot_difficulty_flags(shot, body)
    reasons.extend(difficulty)
    hard_difficulty = any(
        flag.startswith(("coitus_beat:", "sex_arc_beat:", "explicit_local_h3", "l4_contact:"))
        for flag in difficulty
    )
    restricted = bool(reasons) and (
        heat_phase in _RESTRICTED_PHASES or wardrobe in _RESTRICTED_WARDROBE or hard_difficulty
    )
    return {
        "content_class": "restricted_local" if restricted else "general",
        "restricted": restricted,
        "heat_phase": heat_phase or None,
        "wardrobe_state": wardrobe or None,
        "difficulty_flags": difficulty,
        "reasons": reasons,
    }


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
        elif "image_to_video" in operations and (
            "h3" in identity or "comfy-h3" in identity or "minimax" in identity
        ):
            # 5090 MiniMax H3 native-audio dialogue (preferred for restricted).
            value["lane"] = "local_h3"
        elif "image_to_video" in operations and "grok" in identity:
            value["lane"] = "grok_imagine_video"
        # Frozen post-lipsync tools (LatentSync / InfiniteTalk / MuseTalk) are
        # intentionally not mapped into competition lanes.
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
    classification = classify_shot_content(shot, dsl=dsl)
    heat_phase = str(classification.get("heat_phase") or "")
    wardrobe = str(classification.get("wardrobe_state") or "")
    restricted = bool(classification.get("restricted"))
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
    # Dual-lane recommendation (cloud Grok/FRW vs local MiniMax H3).
    # Soft-lock when the *film* opts in (h3.enabled / hybrid_h3 / h3_primary),
    # not merely because the process env profile is hybrid_h3.
    try:
        from film_spec import resolve_h3_config

        h3_cfg = resolve_h3_config(spec)
    except Exception:
        h3_cfg = {
            "enabled": False,
            "audio_policy": "prefer_native",
            "max_duration_sec": 8,
        }
    film_profile = str(spec.get("_i2v_profile") or "").strip().lower()
    h3_raw = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
    # Prefer resolved config (adult-max auto-enable) over raw film-spec only.
    is_h3_primary = film_profile == "h3_primary"
    is_ltx23_adult = film_profile == "ltx23_adult"
    is_ltx23_primary = film_profile == "ltx23_primary"
    h3_enabled = (
        bool(h3_cfg.get("enabled"))
        or h3_raw.get("enabled") is True
        or film_profile
        in {
            "hybrid_h3",
            "h3_primary",
            "ltx23_adult",
        }
    )
    lanes = spec.get("motion_lanes") if isinstance(spec.get("motion_lanes"), dict) else {}
    dialogue = bool(
        shot.get("lipsync") is True
        or shot.get("speaker_on_camera") is True
        or str(shot.get("screen_mode") or "") == "on_camera"
    )
    # Safe (non-restricted) LTX 2.3 native-audio lane: opt-in via profile or motion_lanes.
    dialogue_lane_cfg = str(
        lanes.get("dialogue_safe_cloud") or lanes.get("dialogue") or ""
    ).strip().lower()
    use_ltx_safe_audio = (
        is_ltx23_adult
        or is_ltx23_primary
        or dialogue_lane_cfg
        in {
            "frw_ltx23",
            "frw-ltx23",
            "cloud_ltx23_audio",
            "ltx23",
            "ltx2.3",
        }
        or lanes.get("allow_ltx_dialogue") is True
    )
    recommended_lane = "cloud_grok"
    recommended_provider = "grok"
    recommended_weapon: str | None = None
    audio_policy = "carry_parent_dialogue" if parent_shot_id is not None else None
    if dialogue and identity_lock:
        # Native-audio IRON: post lipsync frozen. Generators = Grok Video / H3 / opt-in LTX2.3.
        # Restricted + bare meat dialogue → H3 hard (never silent cloud meat).
        if restricted or is_h3_primary:
            recommended_lane = str(lanes.get("dialogue_restricted_local") or "local_dialogue_h3")
            recommended_provider = "comfy-h3"
            recommended_weapon = "minimax-h3-i2v-pilot"
            audio_policy = str(h3_cfg.get("audio_policy") or "prefer_native")
            if h3_enabled and not provider_lock:
                provider_lock = "comfy-h3"
        elif use_ltx_safe_audio:
            recommended_lane = str(lanes.get("dialogue_safe_cloud") or "cloud_ltx23_audio")
            recommended_provider = "frw-ltx23"
            recommended_weapon = "ltx23-img2video-audio"
            audio_policy = "prefer_native"
            if not provider_lock and film_profile in {"ltx23_adult", "ltx23_primary"}:
                provider_lock = "frw-ltx23"
        else:
            recommended_lane = str(lanes.get("dialogue_safe_cloud") or "cloud_dialogue_grok")
            recommended_provider = "grok"
            recommended_weapon = "grok-imagine-video"
            audio_policy = "prefer_native"
    elif restricted and identity_lock:
        recommended_lane = str(lanes.get("restricted_local") or "local_h3")
        recommended_provider = "comfy-h3"
        recommended_weapon = "minimax-h3-i2v-pilot"
        audio_policy = str(h3_cfg.get("audio_policy") or "prefer_native")
        # Soft-lock restricted meat to H3 when hybrid/h3/ltx23_adult enabled.
        if h3_enabled and not provider_lock:
            provider_lock = "comfy-h3"
    elif role in {"env", "bridge", "insert"} and not identity_lock:
        # h3_primary: unlimited local T2V for no-face env/bridge (no FRW spend).
        if is_h3_primary and h3_enabled:
            recommended_lane = str(lanes.get("env") or "local_h3_t2v")
            recommended_provider = "comfy-h3"
            recommended_weapon = "minimax-h3-t2v-pilot"
            audio_policy = str(h3_cfg.get("audio_policy") or "prefer_native")
            operation = "text_to_video"
            if not provider_lock:
                provider_lock = "comfy-h3"
        else:
            recommended_lane = str(lanes.get("env") or "cloud_env")
            recommended_provider = "frw"
            recommended_weapon = None
            operation = "text_to_video"
    elif identity_lock:
        if is_h3_primary and h3_enabled:
            # Film-wide local primary: setup/soft also stays on 5090 H3.
            recommended_lane = str(lanes.get("setup_non_sensitive") or "local_h3")
            recommended_provider = "comfy-h3"
            recommended_weapon = "minimax-h3-i2v-pilot"
            audio_policy = str(h3_cfg.get("audio_policy") or "prefer_native")
            if not provider_lock:
                provider_lock = "comfy-h3"
        elif is_ltx23_adult or (is_ltx23_primary and use_ltx_safe_audio):
            # Soft / non-restricted hero under ltx23_adult → LTX native-audio I2V.
            recommended_lane = str(lanes.get("setup_non_sensitive") or "cloud_ltx23_audio")
            recommended_provider = "frw-ltx23"
            recommended_weapon = "ltx23-img2video-audio"
            audio_policy = "prefer_native"
            if not provider_lock:
                provider_lock = "frw-ltx23"
        else:
            recommended_lane = str(lanes.get("setup_non_sensitive") or "cloud_grok")
            recommended_provider = "grok"
    recommended_still = (
        "comfy_lan" if (restricted and identity_lock) or (is_h3_primary and restricted) else "grok"
    )
    # Film-core payload for motion prompt spine (shared Grok/H3).
    try:
        from motion_prompt_spine import core_fields

        core = core_fields(spec, shot)
    except Exception:
        core = {}
    continuity = str(dsl.get("chain_mode") or "").lower() == "continue" or bool(
        core.get("continuity_required")
    )
    return {
        "schema_version": 1,
        "kind": "ai-film-shot-intent",
        "shot_id": shot_id,
        "shot_role": role,
        "operation": operation,
        "content_class": "restricted_local" if restricted else "general",
        "identity_lock": identity_lock,
        "continuity_required": continuity,
        "quality_tier": tier,
        "provider_lock": provider_lock or None,
        "recommended_lane": recommended_lane,
        "recommended_provider": recommended_provider,
        "recommended_weapon": recommended_weapon,
        "recommended_still_provider": recommended_still,
        "h3_enabled": bool(h3_enabled),
        "difficulty_flags": list(classification.get("difficulty_flags") or []),
        "route_reasons": list(classification.get("reasons") or []),
        "max_duration_sec": float(h3_cfg.get("max_duration_sec") or 8)
        if recommended_provider == "comfy-h3"
        else None,
        "parent_shot_id": parent_shot_id,
        "broll_kind": broll_kind,
        "editorial_only": parent_shot_id is not None,
        "audio_policy": audio_policy,
        "heat_phase": heat_phase or None,
        "wardrobe_state": wardrobe or None,
        # Motion core (P0 · 2026-08-04) — consumed by prompt spine / gates
        "dramatic_function": core.get("dramatic_function"),
        "want_beat": core.get("want_beat"),
        "motion_tier": core.get("motion_tier"),
        "spoken_text": core.get("spoken_text"),
        "screen_mode": core.get("screen_mode"),
        "speaker": core.get("speaker"),
        "has_action_core": core.get("has_action_core"),
        "action_summary": core.get("action_summary"),
        "camera_prompt": core.get("camera_prompt"),
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
    if lane in {"frw-api", "local"}:
        receipt = _bound_capability_receipt(base, capability)
        if receipt is None:
            reasons.append("CAPABILITY_EVIDENCE_UNBOUND")
        elif lane == "frw-api" and not _frw_api_receipt_ready(base, receipt):
            reasons.append("FRW_API_I2V_CANARY_UNVERIFIED")
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
    if provider == "frw" and ("img2video" in identity or "frw-api-i2v" in identity):
        return "frw-api"
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


def _frw_api_receipt_ready(base: Path, receipt: dict[str, Any]) -> bool:
    model = str(receipt.get("provider_model") or receipt.get("model") or "").strip()
    return bool(
        receipt.get("ok") is True
        and model
        and receipt.get("full_decode_ok") is True
        and receipt.get("human_review") == "approved"
        and _receipt_output_is_bound(base, receipt)
    )


def _queue_lane_idle(value: Any) -> bool:
    return (type(value) is int and value == 0) or (isinstance(value, list) and not value)


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
        and _queue_lane_idle(queue.get("running"))
        and _queue_lane_idle(queue.get("pending"))
    )


def _action_provider_priority(capability: dict[str, Any]) -> int:
    return {
        "frw-ltx": 3,
        "frw-api": 2,
        "grok": 1,
    }.get(_action_lane(capability), 0)


def _is_cloud_capability(capability: dict[str, Any]) -> bool:
    """Classify only the first-party cloud lanes; legacy snapshots remain compatible."""
    provider = str(capability.get("provider") or "").strip().lower()
    resource = str(capability.get("resource") or "").strip().lower()
    if provider not in {"frw", "grok"}:
        return False
    return (
        resource == "cloud"
        or resource.startswith("api:")
        or resource
        in {
            "frw-cloud",
            "grok-in-session",
        }
        or not resource.startswith(("gpu:", "m1-", "local"))
    )


def _is_local_capability(capability: dict[str, Any]) -> bool:
    resource = str(capability.get("resource") or "").strip().lower()
    provider = str(capability.get("provider") or "").strip().lower()
    return resource.startswith(("gpu:", "m1-", "local")) or provider.startswith(
        ("comfy", "local", "private-")
    )


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

    # A healthy FRW/Grok cloud capability reserves scarce local executors.  A
    # transient cloud task failure is recorded by the orchestration queue, not
    # reinterpreted here as a capability gap.
    if any(_is_cloud_capability(item[2]) for item in viable):
        retained: list[tuple[tuple[int, int, int, int, int], str, dict[str, Any]]] = []
        for rank, capability_id, raw in viable:
            if _is_local_capability(raw):
                rejected.append(
                    {
                        "capability_id": capability_id,
                        "provider": raw.get("provider"),
                        "model": raw.get("model"),
                        "reasons": ["CLOUD_CAPABILITY_AVAILABLE"],
                    }
                )
            else:
                retained.append((rank, capability_id, raw))
        viable = retained

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
            ["local_h3"]
            if competition.get("selected_route") == "local_h3"
            else ["grok_imagine_video"]
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
            "primary_grok_native": "grok_imagine_video",
            "alt_h3_native": "local_h3",
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
